"""Configuration for context management, in the style of ``agents.ModelSettings``."""

from __future__ import annotations

from dataclasses import dataclass

from .context_store import DEFAULT_MAX_FILE_BYTES
from .prompts import CONTEXT_PROMPT


@dataclass
class ContextSettings:
    """Limits and guidance for how an agent's context is managed."""

    budget: int = 32_768
    """Text-token budget with o200k; excludes tool schemas, API framing, and media costs."""

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

    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    """Maximum context-file bytes for the built-in local and sandbox stores."""

    def __post_init__(self) -> None:
        for name in ("budget", "reserve", "protect", "max_file_bytes"):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} must be an integer")
        if self.budget <= 0 or not 0 <= self.reserve < self.budget:
            raise ValueError("budget must be positive and reserve must satisfy 0 <= reserve < budget")
        if self.protect < 0:
            raise ValueError("protect must be non-negative")
        if self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")

    @property
    def limit(self) -> int:
        return self.budget - self.reserve
