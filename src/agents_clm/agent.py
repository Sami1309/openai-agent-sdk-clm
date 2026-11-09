"""``CLMAgent``: an SDK agent that manages its own context."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Generic

from agents import Agent
from agents.run_context import TContext

from .context_store import LocalContextStore
from .live_context import LiveContext
from .settings import ContextSettings
from .shell import LocalShell


@dataclass
class CLMAgent(Agent[TContext], Generic[TContext]):
    """An ``Agent`` whose context is a file it edits, per arXiv:2609.37725.

    Run it with ``CLMRunner``. The live context persists across runs of the same agent.
    """

    context_settings: ContextSettings = field(default_factory=ContextSettings)
    """Budget and guidance for managing the context."""

    workdir: str | Path | None = None
    """Workspace for the context file and the agent's commands. Defaults to a temporary directory."""

    allow_unsandboxed: bool = False
    """Allow model-written commands to run without an OS sandbox on non-macOS platforms."""

    live: LiveContext | None = None
    """The live context. Pass your own to change where or how the context is stored."""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.live is None:
            workdir = Path(self.workdir or tempfile.mkdtemp(prefix="clm_")).resolve()
            self.live = LiveContext(self.context_settings, store=LocalContextStore.in_workdir(workdir))
            if not any(getattr(t, "name", None) == "bash" for t in self.tools):
                shell = LocalShell(workdir, allow_unsandboxed=self.allow_unsandboxed)
                self.tools = [*self.tools, shell.tool()]
        if self.model_settings.parallel_tool_calls is None:
            # Two simultaneous commands could both rewrite the context file.
            self.model_settings = replace(self.model_settings, parallel_tool_calls=False)
