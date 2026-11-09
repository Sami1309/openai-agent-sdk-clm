"""Exceptions raised during a run, in the style of ``agents.exceptions``."""

from __future__ import annotations

from agents import AgentsException


class ContextBudgetExceeded(AgentsException):
    """The next model call would not fit in the context budget, so the run ends."""

    def __init__(self, tokens: int, limit: int) -> None:
        super().__init__(f"Context of {tokens} tokens exceeds the {limit}-token limit.")
        self.tokens = tokens
        self.limit = limit
