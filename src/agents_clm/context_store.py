"""Where the context file lives. Implement ``ContextStore`` to keep it somewhere else."""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import Protocol, runtime_checkable

CONTEXT_FILE = ".live_ctx/LIVE_CTX_MAIN.txt"


@runtime_checkable
class ContextStore(Protocol):
    """Storage for the context file, reachable by the tools the agent edits it with."""

    location: str
    """The path the agent should use to edit the file."""

    async def read(self) -> str | None:
        """Return the file's text, or None if it does not exist."""

    async def write(self, text: str) -> None:
        """Replace the file's text."""


def file_name(store: ContextStore) -> str:
    return PurePath(store.location).name


class LocalContextStore:
    """The context file on the local filesystem."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.location = str(self.path)

    @classmethod
    def in_workdir(cls, workdir: str | Path) -> LocalContextStore:
        return cls(Path(workdir) / CONTEXT_FILE)

    async def read(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return None

    async def write(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")
