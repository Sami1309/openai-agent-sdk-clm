"""Run official ContextBench levels and write results to ``runs/`` for the dashboard.

    python -m benchmarks.run --scripted            # offline, no API key, plumbing only
    python -m benchmarks.run --profile pilot       # one rung per family, one seed
    python -m benchmarks.run --profile figure2     # the paper's Figure 2 ladder (spends real money)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from agents import ModelSettings, set_default_openai_client
from openai import AsyncOpenAI
from openai.types.shared import Reasoning
from agents_clm import UsageTrackingResponsesModel

from .harnesses import METHODS, run_one
from .provenance import provenance
from .scripted import ScriptedModel, needle_policy
from .suite import build_instance

RUNS = Path(__file__).resolve().parent.parent / "runs"
# USD per 1M tokens: (input, cached input, output). https://developers.openai.com/api/docs/models
PRICES = {
    "gpt-5.4": (2.50, 0.25, 15.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.5": (5.00, 0.50, 30.00),
}
PILOT = {
    "needle_retention": ["K4-C24"],
    "kv_store": ["R1000"],
    "sudoku_sketchpad": ["t30"],
    "log_triage": ["L1600"],
}
FIGURE2 = {
    "needle_retention": ["K4-C8", "K4-C24", "K8-C60", "K2-C192"],
    "kv_store": ["R520", "R1000", "R4000", "R16000"],
    "sudoku_sketchpad": ["t15", "t30", "t60", "t100"],
    "log_triage": ["L640", "L1600", "L3200"],
}
PROFILES: dict[str, dict[str, Any]] = {
    "pilot": {"levels": PILOT, "seeds": [42]},
    "figure2": {"levels": FIGURE2, "seeds": [42]},
    "scripted": {"levels": {"needle_retention": ["K4-C8", "K4-C24"]}, "seeds": [42], "methods": ["base", "clm"]},
}


def usd_cost(model: str, record: dict[str, Any]) -> float | None:
    prices = PRICES.get(model)
    if prices is None:
        return None
    cached = record["api_cached_tokens"]
    fresh = record["api_input_tokens"] - cached
    return (fresh * prices[0] + cached * prices[1] + record["generated_tokens"] * prices[2]) / 1e6


def validate_carry(earlier: dict[str, Any], *, source: str, model: str, reasoning: str | None, budget: int,
                   code_fingerprint: str | None = None) -> None:
    """Do not relabel old results as measurements of a different experiment."""
    expected = {"source": source, "model": model, "reasoning": reasoning, "budget": budget}
    if code_fingerprint is not None:
        expected["code_fingerprint"] = code_fingerprint
    mismatched = [name for name, value in expected.items() if earlier.get(name) != value]
    if mismatched:
        raise ValueError(f"Cannot carry results with different {', '.join(mismatched)}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", choices=["pilot", "figure2"], default="pilot")
    parser.add_argument("--scripted", action="store_true", help="use a scripted fake model (no API key)")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning", default="default", help="reasoning effort, or 'default' to omit it")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--tasks", nargs="+", choices=list(FIGURE2), help="only these families")
    parser.add_argument("--levels", nargs="+", help="only these levels within the selected profile and families")
    parser.add_argument("--methods", nargs="+", choices=METHODS, help="only these methods")
    parser.add_argument("--seeds", nargs="+", type=int, help="override the profile's seeds")
    parser.add_argument("--max-usd", type=float, default=30.0, help="start no new run past this estimated spend")
    parser.add_argument("--carry", help="reuse finished results from this earlier run id instead of rerunning them")
    args = parser.parse_args()
    if args.concurrency <= 0 or not math.isfinite(args.max_usd) or args.max_usd <= 0:
        parser.error("--concurrency and --max-usd must be positive; --max-usd must be finite")
    if not args.scripted and args.model not in PRICES:
        parser.error("Add the model's token prices to PRICES before running a paid evaluation")

    if not args.scripted and not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Use --scripted for an offline run.", file=sys.stderr)
        return 2

    name = "scripted" if args.scripted else args.profile
    profile = PROFILES[name]
    methods = args.methods or profile.get("methods") or list(METHODS)
    seeds = args.seeds or profile["seeds"]
    levels = {f: v for f, v in profile["levels"].items() if not args.tasks or f in args.tasks}
    if args.levels:
        available = {level for family in levels.values() for level in family}
        if set(args.levels) - available:
            parser.error("--levels must belong to the selected profile and families")
        levels = {f: [level for level in ls if level in args.levels] for f, ls in levels.items()}
    matrix = [(f, level, seed, m) for f, ls in levels.items() for level in ls for seed in seeds for m in methods]
    if not matrix:
        parser.error("No evaluations match the selected profile and families")
    metadata = provenance()

    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{name}"
    out = RUNS / run_id
    out.mkdir(parents=True)
    source = "scripted" if args.scripted else "live"
    settings = ModelSettings(max_tokens=8192)
    client = None
    if not args.scripted:
        client = AsyncOpenAI(max_retries=8, timeout=300)
        set_default_openai_client(client)
        if args.reasoning != "default":
            settings = ModelSettings(max_tokens=8192, reasoning=Reasoning(effort=args.reasoning))

    print(f"{run_id}: {len(matrix)} runs, model {'scripted' if args.scripted else args.model}, cap ${args.max_usd:g}")
    # Generate up front so concurrent runs share the cache. Cheapest first, so the spending
    # guard can only drop the most expensive runs.
    weight = {"base": 0.2, "clm": 1.0, "summary": 3.0}
    matrix.sort(key=lambda row: len(build_instance(row[0], row[1], row[2]).ops) * weight[row[3]])

    limiter = asyncio.Semaphore(args.concurrency)
    results: list[dict[str, Any]] = []
    state = {"spent": 0.0, "skipped": 0}
    carried_usd = 0.0
    if args.carry:
        earlier = json.loads((RUNS / args.carry / "summary.json").read_text())
        try:
            validate_carry(
                earlier, source=source, model="scripted" if args.scripted else args.model,
                reasoning=None if args.scripted else args.reasoning, budget=32_768,
                code_fingerprint=metadata["code_fingerprint"],
            )
        except ValueError as exc:
            parser.error(str(exc))
        wanted = set(matrix)
        for record in earlier["results"]:
            row = (record["task"], record["level"], record["seed"], record["method"])
            if row in wanted and record["score"] is not None:
                shutil.copy(RUNS / args.carry / record["trace_file"], out / record["trace_file"])
                results.append(record)
                carried_usd += record.get("usd") or 0.0
                matrix.remove(row)
        print(f"Carried {len(results)} results (${carried_usd:.2f}) from {args.carry}; {len(matrix)} runs to do")

    planned = len(matrix) + len(results)

    def write_summary() -> None:
        payload = {
            "run_id": run_id,
            "source": source,
            "model": "scripted" if args.scripted else args.model,
            "reasoning": None if args.scripted else args.reasoning,
            "budget": 32_768,
            "planned": planned,
            "estimated_usd": round(state["spent"] + carried_usd, 2),
            "skipped_over_budget": state["skipped"],
            "results": results,
            **metadata,
        }
        (out / "summary.json").write_text(json.dumps(payload, indent=1))

    async def one(family: str, level: str, seed: int, method: str) -> None:
        async with limiter:
            if state["spent"] >= args.max_usd:
                state["skipped"] += 1
                write_summary()
                return
            model: Any = ScriptedModel(needle_policy(method)) if args.scripted else UsageTrackingResponsesModel(args.model, client)
            output = await run_one(family, level, seed, method, model, settings=settings)
        record = output["record"]
        record["usd"] = None if args.scripted else usd_cost(args.model, record)
        state["spent"] += record["usd"] or 0.0
        file_name = f"{family}-{level}-{method}-s{seed}.json"
        record["trace_file"] = file_name
        (out / file_name).write_text(json.dumps(output))
        results.append(record)
        score = "n/a" if record["score"] is None else f"{record['score']:.3f}"
        cost = f" ${record['usd']:.3f}" if record["usd"] is not None else ""
        print(
            f"  {family:17} {level:8} {method:8} s={seed} score={score:>6} {record['terminated']:17} "
            f"ops={record['ops_delivered']}/{record['ops_total']} peak={record['peak_context']:>6} "
            f"calls={record['model_calls']:<4}{cost}{' ' + record['error'][:160] if record['error'] else ''}",
            flush=True,
        )
        write_summary()

    write_summary()
    await asyncio.gather(*(one(*row) for row in matrix))
    if client is not None:
        await client.close()
    write_summary()
    errors = sum(r["terminated"] == "error" for r in results)
    print(f"Wrote {out}; estimated ${state['spent']:.2f}; {errors} errors; {state['skipped']} skipped")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
