"""``CLMRunner``: run an agent whose context is its own to manage."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

from agents import Agent, AgentsException, MaxTurnsExceeded, RunConfig, Runner, RunState, UserError

from .agent import CLMAgent
from .exceptions import ContextBudgetExceeded
from .live_context import LiveContext


def _live_context(agent: Agent[Any]) -> LiveContext:
    if isinstance(agent, CLMAgent) and agent.live is not None:
        return agent.live
    for capability in getattr(agent, "capabilities", ()):
        if getattr(capability, "type", None) == "context_file":
            return capability.live
    raise UserError("CLMRunner requires a CLMAgent, or a SandboxAgent with the ContextFile capability.")


def _configure(live: LiveContext, run_config: RunConfig | dict[str, Any] | None, kwargs: dict[str, Any]) -> RunConfig:
    for name in ("session", "conversation_id", "previous_response_id", "auto_previous_response_id"):
        if kwargs.get(name) is not None and (name != "auto_previous_response_id" or kwargs[name]):
            raise UserError(
                f"{name} is not supported: it stores the context outside the agent's control. "
                "Run the same agent again to continue a conversation."
            )
    config = RunConfig(**run_config) if isinstance(run_config, dict) else run_config or RunConfig()
    if config.call_model_input_filter is not None:
        raise UserError("CLMRunner sets call_model_input_filter itself.")
    return replace(config, call_model_input_filter=live)


class CLMRunner:
    """Like ``agents.Runner``, for an agent that manages its own context."""

    @staticmethod
    async def run(
        agent: Agent[Any], input: Any, *, run_config: RunConfig | dict[str, Any] | None = None,
        checkpoint: str | Path | None = None, **kwargs: Any,
    ) -> Any:
        live = _live_context(agent)
        if isinstance(input, RunState):
            raise UserError("RunState resumption is not supported by CLMRunner. Use the SDK Runner for resumable runs.")
        config = _configure(live, run_config, kwargs)
        with live.run_scope():
            try:
                result = await Runner.run(agent, input, run_config=config, **kwargs)
            except Exception as exc:
                if isinstance(exc, ContextBudgetExceeded) and live.trace.steps:
                    rejected = live.trace.reject_last("over_budget")
                    if rejected and getattr(exc, "_clm_preflight_failed", False):
                        live.trace.steps[-1]["provider_input_tokens"] = exc.tokens
                else:
                    live.trace.attach_failure(exc)
                if isinstance(exc, AgentsException) and exc.run_data is not None:
                    if isinstance(exc, MaxTurnsExceeded):
                        await live.finish_max_turns(exc.run_data)
                        if checkpoint is not None:
                            await live._save_checkpoint(checkpoint)
                    live.trace.attach_usage(exc.run_data.context_wrapper.usage)
                raise
            if result.interruptions:
                raise UserError("Tool approval interruptions are not supported by CLMRunner; use the SDK Runner for resumable approvals.")
            await live.finish(result)
            if checkpoint is not None:
                await live._save_checkpoint(checkpoint)
        return result

    @staticmethod
    def run_sync(agent: Agent[Any], input: Any, *, run_config: RunConfig | dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return asyncio.run(CLMRunner.run(agent, input, run_config=run_config, **kwargs))
