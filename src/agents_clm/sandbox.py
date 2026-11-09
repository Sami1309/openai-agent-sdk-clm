"""CLM on SDK sandboxes: a ``Capability`` for ``agents.sandbox.SandboxAgent``.

The context file lives in the sandbox workspace, and the agent edits it with the sandbox's own
shell, so the same agent runs on any sandbox backend the SDK supports.
"""

from __future__ import annotations

import io
from pathlib import PurePosixPath
from typing import Any, Literal

from agents.sandbox.capabilities import Capability
from agents.sandbox.errors import WorkspaceReadNotFoundError
from agents.sandbox.session.base_sandbox_session import BaseSandboxSession
from agents.sandbox.types import User
from agents.sandbox.workspace_paths import SandboxWorkspaceScope
from pydantic import Field, field_validator

from .context_store import CONTEXT_FILE, DEFAULT_MAX_FILE_BYTES
from .exceptions import ContextFileTooLarge
from .live_context import LiveContext
from .settings import ContextSettings


class SandboxContextStore:
    """The context file inside a sandbox session's workspace."""

    def __init__(self, session: BaseSandboxSession, location: str, *, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
        self.session = session
        self.location = location
        self.path = PurePosixPath(location)
        self.user: User | None = None
        self._detached = False
        self._text: str | None = None
        self.max_bytes = max_bytes
        self._read_error: ContextFileTooLarge | None = None

    async def read(self) -> str | None:
        if self._detached:
            if self._read_error is not None:
                raise self._read_error
            return self._text
        try:
            if self.user is None:
                data = await self.session.read_bounded(self.path, max_bytes=self.max_bytes + 1)
            else:
                # The SDK's bounded-read API has no user override. Preserve run_as identity.
                handle = await self.session.read(self.path, user=self.user)
                with handle:
                    data = handle.read(self.max_bytes + 1)
        except (FileNotFoundError, WorkspaceReadNotFoundError):
            return None
        if len(data if isinstance(data, bytes) else data.encode("utf-8")) > self.max_bytes:
            raise ContextFileTooLarge(self.max_bytes)
        return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data

    async def write(self, text: str) -> None:
        if len(text.encode("utf-8")) > self.max_bytes:
            raise ContextFileTooLarge(self.max_bytes)
        if not self._detached:
            await self.session.write(self.path, io.BytesIO(text.encode("utf-8")), user=self.user)
        self._text = text
        self._read_error = None

    async def detach(self) -> None:
        """Keep final tool edits before the SDK stops and deletes its sandbox."""
        try:
            self._text = await self.read()
        except ContextFileTooLarge as exc:
            # Retain the error for LiveContext to reject the edit after SDK cleanup.
            self._read_error = exc
        self._detached = True


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

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("ContextFile.path must be a non-empty workspace-relative POSIX file path")
        return str(path)

    def model_post_init(self, context: Any) -> None:
        if self.live is None:
            self.live = LiveContext(self.settings, store=_UnboundStore(self.path))

    def clone(self) -> ContextFile:
        # The SDK clones capabilities per run. The live context has to outlive each run.
        return self.model_copy(deep=False)

    def bind(self, session: BaseSandboxSession) -> None:
        super().bind(session)
        store = SandboxContextStore(session, self.path, max_bytes=self.settings.max_file_bytes)
        self.live.store = store
        session.register_pre_stop_hook(store.detach)

    def bind_workspace_scope(self, scope: SandboxWorkspaceScope) -> None:
        super().bind_workspace_scope(scope)
        self.live.store.location = str(scope.model_resource_path(
            workspace_root=self.session.state.manifest.root, workspace_relative_path=self.path,
        ))

    def bind_run_as(self, user: User | None) -> None:
        super().bind_run_as(user)
        self.live.store.user = user

    def required_capability_types(self) -> set[str]:
        return {"shell"}
