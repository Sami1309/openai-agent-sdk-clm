"""Per-call context trace and the paper's prefix-reuse cost (Eq. 3, Appendix C)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import tiktoken

_ENCODING = tiktoken.get_encoding("o200k_base")  # The tokenizer the paper counts budgets with.


def count_text(text: str) -> int:
    return len(_ENCODING.encode(text, disallowed_special=()))


def item_text(item: dict[str, Any]) -> str:
    kind = item.get("type")
    if kind == "function_call":
        return f"{item.get('name', '')} {item.get('arguments', '')}"
    if kind == "function_call_output":
        output = item.get("output")
        return output if isinstance(output, str) else json.dumps(output)
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return json.dumps(item)


def item_role(item: dict[str, Any]) -> str:
    kind = item.get("type")
    if kind == "function_call":
        return "assistant"
    if kind == "function_call_output":
        return "tool"
    return str(item.get("role", kind or "unknown"))


@dataclass(frozen=True)
class FlopsModel:
    """Per-token and per-attention-pair costs from Appendix C (Eqs. 7 and 8)."""

    name: str
    c_token: float
    c_attn: float


# Used as a common yardstick. OpenAI models' architectures are not public, so this answers
# "what would this token trace cost on the paper's reference model?"
QWEN36_27B = FlopsModel("Qwen3.6-27B", c_token=48.70e9, c_attn=3.93e5)


def turn_flops(prompt: int, reused: int, generated: int, model: FlopsModel = QWEN36_27B) -> float:
    """Cost of one turn under prefix caching (Eq. 9)."""
    unmatched = prompt - reused
    attention = 0.5 * (prompt**2 - reused**2) + generated * prompt + 0.5 * generated**2
    return model.c_token * (unmatched + generated) + model.c_attn * attention


class ContextTrace:
    """Records exactly what was sent on every model call."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.texts: dict[str, str] = {}
        self._seen_prefixes: set[str] = set()

    def _intern(self, role: str, text: str) -> tuple[str, int]:
        key = hashlib.sha1(f"{role}\0{text}".encode()).hexdigest()[:16]
        self.texts.setdefault(key, text)
        return key, count_text(text)

    def measure(self, instructions: str | None, items: list[dict[str, Any]]) -> int:
        return sum(count_text(t) for t in [instructions or "", *map(item_text, items)])

    def record(
        self,
        instructions: str | None,
        items: list[dict[str, Any]],
        *,
        kind: str = "turn",
        **extra: Any,
    ) -> int:
        """Log one prompt and return its token count."""
        messages = [("system", instructions or "")]
        messages += [(item_role(i), item_text(i)) for i in items]
        total = reused = 0
        prefix = hashlib.sha1()
        still_matching = True
        keys: list[dict[str, Any]] = []
        new_prefixes: list[str] = []
        for role, text in messages:
            key, tokens = self._intern(role, text)
            keys.append({"role": role, "key": key, "tokens": tokens})
            total += tokens
            prefix.update(key.encode())
            digest = prefix.hexdigest()
            if still_matching and digest in self._seen_prefixes:
                reused += tokens
            else:
                still_matching = False
            new_prefixes.append(digest)
        if kind != "over_budget":
            self._seen_prefixes.update(new_prefixes)
        self.steps.append(
            {
                "step": len(self.steps),
                "kind": kind,
                "tokens": total,
                "reused": reused,
                "generated": 0,
                "messages": keys,
                **extra,
            }
        )
        return total

    def credit_output(self, items: list[dict[str, Any]]) -> None:
        """Attribute newly seen model output to the most recent turn."""
        generated = sum(count_text(item_text(i)) for i in items if item_role(i) == "assistant")
        if generated and self.steps:
            self.steps[-1]["generated"] += generated

    def attach_usage(self, usage: Any) -> None:
        """Replace estimates with provider-reported usage when it lines up one-to-one."""
        turns = [s for s in self.steps if s["kind"] == "turn"]
        entries = list(getattr(usage, "request_usage_entries", None) or [])
        if not entries or len(entries) > len(turns):
            return
        # A driver may call the runner repeatedly, so these are the most recent turns.
        for step, entry in zip(turns[-len(entries) :], entries, strict=True):
            step["generated"] = entry.output_tokens
            step["api_input_tokens"] = entry.input_tokens
            step["api_cached_tokens"] = entry.input_tokens_details.cached_tokens
            step["api_reasoning_tokens"] = entry.output_tokens_details.reasoning_tokens

    @property
    def last_sent_text(self) -> str:
        for step in reversed(self.steps):
            if step["kind"] != "over_budget":
                return "\n".join(self.texts[m["key"]] for m in step["messages"])
        return ""

    def summary(self, model: FlopsModel = QWEN36_27B) -> dict[str, Any]:
        charged = [s for s in self.steps if s["kind"] in ("turn", "compaction")]
        prefilled = sum(s["tokens"] - s["reused"] for s in charged)
        flops = sum(turn_flops(s["tokens"], s["reused"], s["generated"], model) for s in charged)
        return {
            "model_calls": len(charged),
            "peak_context": max((s["tokens"] for s in charged), default=0),
            "prompt_tokens": sum(s["tokens"] for s in charged),
            "prefilled_tokens": prefilled,
            "generated_tokens": sum(s["generated"] for s in charged),
            "edits_applied": sum(1 for s in charged if (s.get("edit") or {}).get("status") == "applied"),
            "reference_pflops": flops / 1e15,
            "reference_model": model.name,
            "api_input_tokens": sum(s.get("api_input_tokens", 0) for s in charged),
            "api_cached_tokens": sum(s.get("api_cached_tokens", 0) for s in charged),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"steps": self.steps, "texts": self.texts, "summary": self.summary()}
