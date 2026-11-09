"""CLM on SDK sandboxes: a ``Capability`` for ``agents.sandbox.SandboxAgent``.

The context file lives in the sandbox workspace, and the agent edits it with the sandbox's own
shell, so the same agent runs on any sandbox backend the SDK supports.
"""

from __future__ import annotations

import io
from pathlib import PurePosixPath
from typing import Any, Literal

from agents.sandbox.capabilities import Capability
from agents.sandbox.session.base_sandbox_session import BaseSandboxSession
from pydantic import Field

from .context_store import CONTEXT_FILE
from .live_context import LiveContext
from .settings import ContextSettings


class SandboxContextStore:
    """The context file inside a sandbox session's workspace."""

    def __init__(self, session: BaseSandboxSession, location: str) -> None:
        self.session = session
        self.location = location

    async def read(self) -> str | None:
        try:
            handle = await self.session.read(PurePosixPath(self.location))
        except Exception as exc:
            if "not found" in str(exc).lower() or isinstance(exc, FileNotFoundError):
                return None
            raise
        with handle:
            data = handle.read()
        return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data

    async def write(self, text: str) -> None:
        await self.session.write(PurePosixPath(self.location), io.BytesIO(text.encode("utf-8")))


class _UnboundStore:
    """Holds the place of the sandbox store until the session starts."""

    def __init__(self, location: str) -> None:
        self.location = location

    async def read(self) -> str | None:
        return None

    async def write(self, text: str) -> None:
        raise RuntimeError("The ContextFile capability is not bound to a sandbox session.")


class ContextFile(Capability):
    """Makes a ``SandboxAgent`` its own CLM. Requires the ``Shell`` capability and ``CLMRunner``."""

    type: Literal["context_file"] = "context_file"
    settings: ContextSettings = Field(default_factory=ContextSettings)
    path: str = CONTEXT_FILE
    """Location of the context file, relative to the workspace root."""
    live: LiveContext | None = Field(default=None, exclude=True)

    def model_post_init(self, context: Any) -> None:
        if self.live is None:
            self.live = LiveContext(self.settings, store=_UnboundStore(self.path))

    def clone(self) -> ContextFile:
        # The SDK clones capabilities per run. The live context has to outlive each run.
        return self.model_copy(deep=False)

    def bind(self, session: BaseSandboxSession) -> None:
        super().bind(session)
        self.live.store = SandboxContextStore(session, self.path)

    def required_capability_types(self) -> set[str]:
        return {"shell"}
