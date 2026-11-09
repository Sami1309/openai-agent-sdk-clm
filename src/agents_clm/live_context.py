"""``LiveContext``: the agent's context, held as a file the agent can edit.

This replaces the SDK's append-only context with c_{t+1} = f(c_t) (paper Eq. 2). The file is
the context, and each model call sends whatever the file now says.
"""

from __future__ import annotations

from typing import Any

from agents.run_config import ModelInputData

from .context_file import ContextFileFormat, Item, Turn
from .context_manager import ContextManager
from .context_store import ContextStore, file_name
from .settings import ContextSettings


class LiveContext(ContextManager):
    """A ``call_model_input_filter`` that makes a file the agent's live context."""

    def __init__(
        self,
        settings: ContextSettings | None = None,
        *,
        store: ContextStore,
        file_format: ContextFileFormat | None = None,
    ) -> None:
        super().__init__(settings)
        self.store = store
        self.file_format = file_format or ContextFileFormat()
        self.protected: list[Turn] | None = None
        self.turns: list[Turn] = []
        self._written = ""

    @property
    def input_items(self) -> list[Item]:
        """The live context in Responses API form, as the next model call would send it."""
        return self.file_format.to_wire([*(self.protected or []), *self.turns])

    async def read(self) -> str:
        """The context file as it stands, or an empty string if nothing has been written."""
        return await self.store.read() or ""

    def _instructions(self, base: str | None) -> str:
        section = self.settings.prompt.format(limit=self.limit, path=self.store.location)
        skill = f"\n\n{self.settings.skill}" if self.settings.skill else ""
        return f"{base or ''}{section}{skill}"

    def _tokens(self, instructions: str, turns: list[Turn]) -> int:
        return self.trace.measure(instructions, self.file_format.to_wire([*(self.protected or []), *turns]))

    async def _sync_edit(self, instructions: str) -> tuple[str, dict[str, Any] | None]:
        """Apply the file's contents to the live context. Returns a note for the model."""
        on_disk = await self.store.read()
        if on_disk is None or on_disk.strip() == self._written.strip():
            return "", None
        candidate = self.file_format.parse(on_disk, self.turns)
        before = self._tokens(instructions, self.turns)
        after = self._tokens(instructions, candidate)
        name = file_name(self.store)
        if after > self.limit and after > before:
            note = f"\n[{name}: edit REJECTED, it would grow context ~{before}->{after} tokens, over the {self.limit}-token limit]"
            return note, {"status": "rejected", "before": before, "after": after}
        self.turns = candidate
        note = f"\n[{name}: edit applied - context ~{before}->{after} tokens, {len(candidate)} turns]"
        return note, {"status": "applied", "before": before, "after": after}

    async def update(self, model_data: ModelInputData, new: list[Item]) -> ModelInputData:
        instructions = self._instructions(model_data.instructions)
        to_turn = self.file_format.item_to_turn
        if self.protected is None:
            protect = self.settings.protect
            self.protected = [t for t in map(to_turn, new[:protect]) if t]
            new = new[protect:]

        note, edit = await self._sync_edit(instructions)
        self._step_info = {"edit": edit} if edit else {}
        fresh = [t for t in map(to_turn, new) if t]
        name = file_name(self.store)
        if edit is None and any(name in (t.raw or {}).get("arguments", "") for t in fresh):
            note = f"\n[{name}: unchanged]"
        self.turns.extend(fresh)

        tool_turns = [t for t in fresh if t.role == "tool"]
        if tool_turns:
            tokens = self._tokens(instructions, self.turns)
            near = self.settings.warn_near_limit and tokens > self.limit - self.settings.reserve
            warn = f" - near the limit, compact {name} now" if near else ""
            tool_turns[-1].set_text(f"{tool_turns[-1].text}{note}\n[context: ~{tokens}/{self.limit} tokens{warn}]")

        await self._write()
        self._step_info["file"] = self._written
        return ModelInputData(input=self.input_items, instructions=instructions)

    async def absorb(self, new: list[Item]) -> None:
        self.turns.extend(t for t in map(self.file_format.item_to_turn, new) if t)
        await self._write()

    async def _write(self) -> None:
        self._written = self.file_format.render(self.turns)
        await self.store.write(self._written)
