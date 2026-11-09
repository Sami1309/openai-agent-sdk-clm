"""Where the context file lives. Implement ``ContextStore`` to keep it somewhere else."""

from __future__ import annotations

import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Protocol, runtime_checkable

from .exceptions import ContextFileTooLarge

CONTEXT_FILE = ".live_ctx/LIVE_CTX_MAIN.txt"
DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024


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
    """The context file on the local filesystem, without following model-created symlinks.

    Paths must have no symlink components. ``in_workdir`` resolves the trusted workspace
    once, before adding the model-controlled context directory.
    """

    def __init__(self, path: str | Path, *, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        self.max_bytes = max_bytes
        self.path = Path(os.path.abspath(path))
        with self._parent_fd(create=True):
            pass
        self.location = str(self.path)

    @classmethod
    def in_workdir(cls, workdir: str | Path, *, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> LocalContextStore:
        return cls(Path(workdir).resolve() / CONTEXT_FILE, max_bytes=max_bytes)

    @contextmanager
    def _parent_fd(self, *, create: bool = False) -> Iterator[int]:
        # Walk via directory descriptors: checking resolve()/is_symlink() first would
        # leave a race between checking the path and opening it on the host.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.path.anchor, flags)
        try:
            for part in self.path.parts[1:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    async def read(self) -> str | None:
        try:
            with self._parent_fd() as parent:
                fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(fd, "rb") as handle:
                    info = os.fstat(handle.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise OSError("The context must be a regular file with a single link")
                    data = handle.read(self.max_bytes + 1)
                    if len(data) > self.max_bytes:
                        raise ContextFileTooLarge(self.max_bytes)
                    return data.decode("utf-8", errors="replace")
        except FileNotFoundError:
            return None

    async def write(self, text: str) -> None:
        data = text.encode("utf-8")
        if len(data) > self.max_bytes:
            raise ContextFileTooLarge(self.max_bytes)
        with self._parent_fd(create=True) as parent:
            name = f".context-{uuid.uuid4().hex}.tmp"
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                # Replacing a symlink is safe; opening it for writing is not.
                os.replace(name, self.path.name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(name, dir_fd=parent)
                except FileNotFoundError:
                    pass
