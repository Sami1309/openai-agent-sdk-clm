"""Versioned conversation checkpoints, separate from the model-editable context file."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from agents import UserError

from .context_file import ContextFileFormat, Turn

MAX_CHECKPOINT_BYTES = 32 * 1024 * 1024


def format_name(file_format: ContextFileFormat) -> str:
    cls = type(file_format)
    return f"{cls.__module__}.{cls.__qualname__}"


def encode_checkpoint(file_format: ContextFileFormat, protected: list[Turn] | None, turns: list[Turn]) -> str:
    return json.dumps({
        "version": 1,
        "format": format_name(file_format),
        "protected": None if protected is None else [asdict(t) for t in protected],
        "turns": [asdict(t) for t in turns],
        "file": file_format.render(turns),
    }, ensure_ascii=False)


def _turns(value: Any, file_format: ContextFileFormat) -> list[Turn]:
    if not isinstance(value, list):
        raise ValueError("Expected a turn list")
    result = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"role", "text", "raw"}:
            raise ValueError("Invalid turn fields")
        if not isinstance(entry["role"], str) or not isinstance(entry["text"], str):
            raise ValueError("Turn role and text must be strings")
        raw = entry["raw"]
        if raw is not None:
            if not isinstance(raw, dict) or file_format.item_to_turn(raw) is None:
                raise ValueError("Invalid structured turn")
        result.append(Turn(**entry))
    file_format.to_wire(result)  # Validate call IDs before touching the destination.
    return result


def decode_checkpoint(text: str, file_format: ContextFileFormat) -> tuple[list[Turn] | None, list[Turn], str]:
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {"version", "format", "protected", "turns", "file"}:
            raise ValueError("Invalid checkpoint fields")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("Unsupported checkpoint version")
        if data["format"] != format_name(file_format):
            raise ValueError("Checkpoint requires the same ContextFileFormat class")
        protected = None if data["protected"] is None else _turns(data["protected"], file_format)
        turns = _turns(data["turns"], file_format)
        if data["file"] != file_format.render(turns):
            raise ValueError("Checkpoint text and structured turns disagree")
        return protected, turns, data["file"]
    except (ValueError, TypeError, KeyError) as exc:
        raise UserError(f"Invalid CLM checkpoint: {exc}") from exc
