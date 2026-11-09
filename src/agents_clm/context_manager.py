"""Context policies, used as ``RunConfig.call_model_input_filter``.

``ContextManager`` keeps the SDK's default behavior (append everything) and adds measurement
and a budget. Subclass it and override ``update`` to implement another policy.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from typing import Any

from agents import ItemHelpers, UserError
from agents.run_config import CallModelData, ModelInputData

from .context_file import Item
from .exceptions import ContextBudgetExceeded
from .metrics import ContextTrace
from .settings import ContextSettings


class ContextManager:
    """Decides what the model receives on each call."""

    def __init__(self, settings: ContextSettings | None = None) -> None:
        self.settings = settings or ContextSettings()
        self.limit = self.settings.limit
        self.trace = ContextTrace()
        self.view: list[Item] = []
        self.attempted: ModelInputData | None = None
        """The most recent input built for the model, including one that was over budget."""
        self._seen = 0
        self._queued: list[Item] = []
        self._step_info: dict[str, Any] = {}
        self._run_lock = threading.Lock()
        self._runner_items: list[Item] = []

    def begin_run(self) -> None:
        """Call before each ``Runner.run``. The runner's item list starts over on every run."""
        self._seen = 0
        self._runner_items = []

    @contextmanager
    def run_scope(self) -> Iterator[None]:
        """Own this conversation for one run, including final context persistence."""
        with self._exclusive():
            self.begin_run()
            yield

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        if not self._run_lock.acquire(blocking=False):
            raise UserError("This live context is already running. Use a separate context per conversation.")
        try:
            yield
        finally:
            self._run_lock.release()

    def _new_items(self, items: list[Item]) -> list[Item]:
        if items[:self._seen] != self._runner_items:
            raise UserError("Runner history was rewritten. Handoffs and history replacement are not supported.")
        return deepcopy(items[self._seen:])

    def enqueue(self, item: Item) -> None:
        """Add an item, such as a new user message, to the next model call."""
        self._queued.append(item)

    async def __call__(self, data: CallModelData[Any], kind: str = "turn") -> ModelInputData:
        items = list(data.model_data.input)
        new = [*self._new_items(items), *deepcopy(self._queued)]
        self.trace.credit_output(new)
        self._step_info = {}
        updated = await self.update(data.model_data, new)
        self._seen = len(items)
        self._runner_items = deepcopy(items)
        self._queued = []
        self.attempted = updated
        tokens = self.trace.measure(updated.instructions, updated.input)
        over = tokens > self.limit
        self.trace.record(
            updated.instructions,
            updated.input,
            kind="over_budget" if over else kind,
            **self._step_info,
        )
        if over:
            raise ContextBudgetExceeded(tokens, self.limit)
        return updated

    async def update(self, model_data: ModelInputData, new: list[Item]) -> ModelInputData:
        """Return what to send, given the items that are new since the last call."""
        self.view.extend(new)
        return ModelInputData(input=list(self.view), instructions=model_data.instructions)

    async def finish(self, result: Any) -> None:
        """Take in the final response, which no later model call would otherwise see."""
        await self._finish_items(result.to_input_list())
        self.trace.attach_usage(result.context_wrapper.usage)

    async def finish_max_turns(self, details: Any) -> None:
        """Retain completed tools when the SDK reaches its model-turn limit."""
        items = ItemHelpers.input_to_new_input_list(details.input)
        items.extend(item.to_input_item() for item in details.new_items)
        await self._finish_items(items)

    async def _finish_items(self, items: list[Item]) -> None:
        new = self._new_items(items)
        self.trace.credit_output(new)
        await self.absorb(new)
        self._seen = len(items)
        self._runner_items = deepcopy(items)

    async def absorb(self, new: list[Item]) -> None:
        self.view.extend(new)
