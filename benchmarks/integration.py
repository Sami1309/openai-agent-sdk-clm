"""Opt-in live API checks for the SDK extension, separate from ContextBench scores.

    uv run --env-file .env python -m benchmarks.integration

Uses real API credits. Each case has a small output and turn limit. Reports contain
usage and assertions, not credentials or full prompts. No live checks run under pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import struct
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any

from agents import ModelBehaviorError, ModelSettings, function_tool
from openai import AsyncOpenAI
from pydantic import BaseModel

from agents_clm import BudgetedResponsesModel, CLMAgent, CLMRunner, ContextBudgetExceeded, ContextSettings

from .run import PRICES, RUNS, usd_cost
from .provenance import provenance

CONFIG = {"tracing_disabled": True}


class ObservedModel(BudgetedResponsesModel):
    """Record provider usage even if the SDK rejects an incomplete response."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.requests: list[dict[str, Any]] = []

    async def _fetch_response(self, *args: Any, **kwargs: Any) -> Any:
        try:
            response = await super()._fetch_response(*args, **kwargs)
        except Exception as exc:
            self._record(getattr(exc, "_clm_response_usage", None), type(exc).__name__)
            raise
        self._record(response.usage, response.status)
        return response

    def _record(self, usage: Any, status: str) -> None:
        self.requests.append({
            "status": status, "counted_input_tokens": self.last_input_tokens,
            "api_input_tokens": usage.input_tokens if usage else 0,
            "api_cached_tokens": (usage.input_tokens_details.cached_tokens or 0) if usage else 0,
            "generated_tokens": usage.output_tokens if usage else 0,
        })


class Answer(BaseModel):
    value: int


async def checkpoint_case(model: ObservedModel, root: Path) -> None:
    calls = []

    @function_tool
    def multiply(a: int, b: int) -> int:
        """Multiply two integers."""
        calls.append((a, b))
        return a * b

    def agent(workdir: str) -> CLMAgent:
        return CLMAgent(name="checkpoint", model=model, tools=[multiply], output_type=Answer,
                        context_settings=model.context_settings, workdir=root / workdir)

    first = agent("first")
    first.model_settings = ModelSettings(tool_choice="multiply")
    result = await CLMRunner.run(first, "Use multiply for 123 * 456. Remember the result.",
                                 checkpoint=root / "state.json", max_turns=4, run_config=CONFIG)
    assert result.final_output.value == 56088
    restored = agent("restored")
    await restored.live.restore_checkpoint(root / "state.json")
    result = await CLMRunner.run(restored, "Return the previous result without using tools.", max_turns=2, run_config=CONFIG)
    assert result.final_output.value == 56088 and calls == [(123, 456)]
    assert all(r["counted_input_tokens"] == r["api_input_tokens"] for r in model.requests)


async def terminal_edit_case(model: ObservedModel, root: Path) -> None:
    agent = CLMAgent(name="terminal-edit", model=model, context_settings=model.context_settings,
                     workdir=root, model_settings=ModelSettings(tool_choice="bash"),
                     tool_use_behavior="stop_on_first_tool")
    await CLMRunner.run(agent, "Use bash to overwrite .live_ctx/LIVE_CTX_MAIN.txt with exactly "
                        "'[[CTX_TURN 1 role=notes]]' followed by a newline and 'terminal-edit-kept'.",
                        max_turns=2, run_config=CONFIG)
    assert any(t.role == "notes" and t.text == "terminal-edit-kept" for t in agent.live.turns)


async def incomplete_case(model: ObservedModel, root: Path) -> None:
    agent = CLMAgent(name="incomplete", model=model, context_settings=model.context_settings, workdir=root)
    try:
        await CLMRunner.run(agent, "Write all integers from 1 to 500 in order. Do not call tools.",
                            max_turns=2, run_config=CONFIG)
    except ModelBehaviorError:
        summary = agent.live.trace.summary()
        assert summary["generated_tokens"] > 0 and summary["api_input_tokens"] > 0
        assert summary["generated_tokens"] == model.requests[-1]["generated_tokens"]
    else:
        raise AssertionError("Expected the 16-token output limit to interrupt the response")


async def schema_budget_case(model: ObservedModel, root: Path) -> None:
    @function_tool
    def unused() -> str:
        """Never executed."""
        raise AssertionError("An over-budget request must not execute tools")

    unused.description = "Large schema description. " * 1500
    agent = CLMAgent(name="schema-budget", model=model, tools=[unused],
                     context_settings=model.context_settings, workdir=root)
    try:
        await CLMRunner.run(agent, "Say hello.", max_turns=1, run_config=CONFIG)
    except ContextBudgetExceeded:
        assert model.last_input_tokens is not None and model.last_input_tokens > model.context_settings.limit
        assert agent.live.trace.summary()["model_calls"] == 0
        assert all(r["api_input_tokens"] == 0 for r in model.requests)
    else:
        raise AssertionError("Expected the tool schema to exceed the input budget")


def red_tile() -> str:
    """A deterministic 64px PNG fixture, generated without an imaging dependency."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack("!2I5B", 64, 64, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0" * 64) * 64))
    png += chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode()


async def image_case(model: ObservedModel, root: Path) -> None:
    @function_tool
    def image() -> list[dict[str, str]]:
        """Return a colored tile."""
        return [{"type": "image", "image_url": red_tile(), "detail": "low"}]

    agent = CLMAgent(name="image", model=model, tools=[image], context_settings=model.context_settings,
                     workdir=root, model_settings=ModelSettings(tool_choice="image"))
    result = await CLMRunner.run(agent, "Call image, then name its dominant color in one word.", max_turns=3, run_config=CONFIG)
    assert "red" in result.final_output.lower()
    assert any(i.get("type") == "function_call_output" and isinstance(i["output"], list) for i in agent.live.input_items)
    assert all(r["counted_input_tokens"] == r["api_input_tokens"] for r in model.requests)


async def phase_case(model: ObservedModel, root: Path) -> None:
    agent = CLMAgent(name="phase", model=model, context_settings=model.context_settings, workdir=root)
    await CLMRunner.run(agent, [
        {"role": "user", "content": "Remember the sentinel: amber-42."},
        {"role": "assistant", "content": "I will remember amber-42.", "phase": "commentary"},
        {"role": "user", "content": "Repeat the sentinel, without calling tools."},
    ], max_turns=2, run_config=CONFIG)
    text = await agent.live.read()
    await agent.live.store.write(text.replace("I will remember amber-42.", "Remembered amber-42."))
    result = await CLMRunner.run(agent, "Repeat it again without tools.", max_turns=2, run_config=CONFIG)
    assert "amber-42" in result.final_output
    assert any(i.get("phase") == "commentary" and i["content"] == "Remembered amber-42." for i in agent.live.input_items)
    assert all(r["counted_input_tokens"] == r["api_input_tokens"] for r in model.requests)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", choices=list(PRICES), default="gpt-5.4-mini")
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required; this suite makes paid API calls")
    out = RUNS / f"{time.strftime('%Y%m%d-%H%M%S')}-integration"
    out.mkdir(parents=True)
    cases = [
        ("checkpoint_and_structured_tool", checkpoint_case, ContextSettings(budget=8000, reserve=2048)),
        ("terminal_edit", terminal_edit_case, ContextSettings(budget=8000, reserve=1024)),
        ("image_tool", image_case, ContextSettings(budget=8000, reserve=1024)),
        ("assistant_phase", phase_case, ContextSettings(budget=8000, reserve=1024)),
        ("schema_budget", schema_budget_case, ContextSettings(budget=1024, reserve=128)),
        ("incomplete_usage", incomplete_case, ContextSettings(budget=8000, reserve=16)),
    ]
    report: dict[str, Any] = {"model": args.model, "results": [], "estimated_usd": 0.0, **provenance()}
    async with AsyncOpenAI(max_retries=1, timeout=90) as client:
        for name, case, settings in cases:
            model = ObservedModel(args.model, client, context_settings=settings)
            error = None
            with tempfile.TemporaryDirectory(prefix="clm_integration_") as directory:
                try:
                    await case(model, Path(directory).resolve())
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
            cost = sum(usd_cost(args.model, r) or 0 for r in model.requests)
            report["estimated_usd"] += cost
            report["results"].append({"case": name, "passed": error is None, "error": error, "requests": model.requests, "usd": cost})
            (out / "summary.json").write_text(json.dumps(report, indent=2))
            print(f"{name}: {'PASS' if error is None else error} (${cost:.4f})", flush=True)
    print(f"Wrote {out}; estimated ${report['estimated_usd']:.4f}", flush=True)
    return int(any(not r["passed"] for r in report["results"]))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
