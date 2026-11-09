"""Configuration for context management, in the style of ``agents.ModelSettings``."""

from __future__ import annotations

from dataclasses import dataclass

from .prompts import CONTEXT_PROMPT


@dataclass
class ContextSettings:
    """Limits and guidance for how an agent's context is managed."""

    budget: int = 32_768
    """Total context size in tokens, counted with the o200k tokenizer."""

    reserve: int = 2_048
    """Tokens kept free for the model's reply. A request above ``budget - reserve`` is refused."""

    protect: int = 1
    """Leading input items pinned outside the editable file, normally the original task."""

    warn_near_limit: bool = True
    """Tell the agent to compact when it comes within ``reserve`` tokens of the limit."""

    skill: str | None = None
    """In-context guidance on how to manage the context (paper Eq. 4)."""

    prompt: str = CONTEXT_PROMPT
    """Explains the context file to the agent. Formatted with ``{limit}`` and ``{path}``."""

    @property
    def limit(self) -> int:
        return self.budget - self.reserve
