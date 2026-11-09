"""Round-trip between Responses API input items and the editable context file.

The file holds one block per turn::

    [[CTX_TURN 1 role=tool]]
    <text exactly as the model saw it>

    [[CTX_TURN 2 role=assistant]]
    ...

The model may rewrite this file however it likes, so parsing is tolerant: headers define
turns, stray text becomes a user note, and empty turns are dropped. Subclass
``ContextFileFormat`` to change how turns are written or read.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

Item = dict[str, Any]

HEADER_RE = re.compile(r"^\[\[CTX_TURN\s+(\d+)\s+role=([A-Za-z_]+)\]\]\s*$", re.M)
OUTPUT_REMOVED = "(output removed from context)"
# Header-like lines inside a turn's text are escaped on render, so a tool result that
# prints such a line (or a forged one) cannot create a new turn when the file is parsed.
_ESCAPE_RE = re.compile(r"^(\\*\[\[CTX_TURN\b)", re.M)
_UNESCAPE_RE = re.compile(r"^\\(\\*\[\[CTX_TURN\b)", re.M)


@dataclass
class Turn:
    role: str
    text: str
    raw: Item | None = None
    """Structured item to send instead of plain text. None means plain text."""

    def set_text(self, text: str) -> None:
        self.text = text
        if self.raw is not None and self.raw.get("type") == "function_call_output":
            self.raw["output"] = text

    def plain(self) -> Item:
        return {"role": "assistant" if self.role == "assistant" else "user", "content": self.text}


def content_text(content: Any) -> tuple[str, bool]:
    """Return the text of a message's content, and whether that text is all of it."""
    if isinstance(content, str):
        return content, True
    parts: list[str] = []
    complete = True
    for part in content or []:
        text = part.get("text") if isinstance(part, dict) else None
        if isinstance(text, str):
            parts.append(text)
        else:
            parts.append("[non-text content]")
            complete = False
    return "\n".join(parts), complete


class ContextFileFormat:
    """Converts between input items, turns, and the text of the context file."""

    def item_to_turn(self, item: Item) -> Turn | None:
        """Convert one input item to a turn, or None if it has no editable text."""
        kind = item.get("type")
        if kind == "reasoning":
            return None  # Opaque to the model, so there is nothing it could edit.
        if kind == "function_call":
            raw = {k: item[k] for k in ("type", "call_id", "name", "arguments")}
            return Turn("assistant", f"{item['name']} {item['arguments']}".strip(), raw)
        if kind == "function_call_output":
            output = item.get("output")
            text = output if isinstance(output, str) else json.dumps(output)
            text = text.strip() or "(no output)"
            return Turn("tool", text, {"type": kind, "call_id": item["call_id"], "output": text})
        if "role" in item:
            text, complete = content_text(item.get("content"))
            text = text.strip()
            if not text:
                return None
            return Turn(item["role"], text, None if complete else dict(item))
        return Turn("assistant", json.dumps(item))

    def render(self, turns: list[Turn]) -> str:
        blocks = [
            f"[[CTX_TURN {i} role={t.role}]]\n{_ESCAPE_RE.sub(r'\\\1', t.text)}"
            for i, t in enumerate(turns, start=1)
        ]
        return "\n\n".join(blocks)

    def parse(self, text: str, previous: list[Turn]) -> list[Turn]:
        """Parse an edited file, recovering structure from ``previous`` where possible.

        An unchanged turn keeps its structure. So does a tool result edited in place, because
        a model shown its past calls as plain text starts writing new calls as plain text too.
        """
        matches = list(HEADER_RE.finditer(text))
        lead = text[: matches[0].start()] if matches else text
        sections: list[tuple[int, str, str]] = [(0, "user", lead)]
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append((int(match.group(1)), match.group(2).lower(), text[match.end() : end]))

        used: set[int] = set()
        turns: list[Turn] = []
        for number, role, body in sections:
            body = _UNESCAPE_RE.sub(r"\1", body).strip()
            if not body:
                continue
            slot = previous[number - 1] if 1 <= number <= len(previous) else None
            candidates = [slot, *previous] if slot is not None else previous
            same = next((t for t in candidates if id(t) not in used and t.role == role and t.text == body), None)
            if same is not None:
                used.add(id(same))
                turns.append(Turn(role, body, same.raw))
            elif slot is not None and id(slot) not in used and role == slot.role == "tool" and slot.raw is not None:
                used.add(id(slot))
                turns.append(Turn(role, body, {**slot.raw, "output": body}))
            else:
                turns.append(Turn(role, body))
        return turns

    def to_wire(self, turns: list[Turn]) -> list[Item]:
        """Build input items. A call that lost its output stays a call; an orphaned output is text."""
        output_at: dict[str, int] = {}
        call_at: dict[str, int] = {}
        for i, turn in enumerate(turns):
            kind = turn.raw.get("type") if turn.raw is not None else None
            if kind == "function_call_output":
                output_at[turn.raw["call_id"]] = i
            elif kind == "function_call":
                call_at[turn.raw["call_id"]] = i

        items: list[Item] = []
        for turn in turns:
            kind = turn.raw.get("type") if turn.raw is not None else None
            if kind in ("function_call", "function_call_output"):
                call_id = turn.raw["call_id"]
                paired = call_at.get(call_id, len(turns)) < output_at.get(call_id, -1)
                if paired:
                    items.append(turn.raw)
                elif kind == "function_call":
                    items += [turn.raw, {"type": "function_call_output", "call_id": call_id, "output": OUTPUT_REMOVED}]
                else:
                    items.append(turn.plain())
            else:
                items.append(turn.raw if turn.raw is not None else turn.plain())
        return items
