"""Optional provider-side budget enforcement for the OpenAI Responses API.

The request builder and terminal-response handling below are SDK 0.24 integration points.
Keep the SDK version bound and the request-parity tests when upgrading that dependency.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from agents import ModelSettings, UserError
from agents.models.openai_responses import (
    OpenAIResponsesModel,
    _mark_transport_request_without_usage,
    response_terminal_failure_error,
)
from openai import AsyncOpenAI
from openai.types.responses import Response

from .exceptions import ContextBudgetExceeded
from .settings import ContextSettings

_COUNT_FIELDS = {
    "model", "input", "instructions", "tools", "text", "tool_choice",
    "parallel_tool_calls", "reasoning", "truncation",
}
_NON_CONTEXT_EXTRA_ARGS = {"prompt_cache_key", "service_tier", "safety_identifier"}


class BudgetedResponsesModel(OpenAIResponsesModel):
    """Count the serialized request before generation and cap output at ``reserve``.

    Counts schemas, framing, and media using ``responses.input_tokens.count``. Each model
    request adds a counting round trip. A counting failure aborts generation; no estimate
    fallback is used. Server-managed history, stored prompts, payload overrides, automatic
    truncation/compaction, and streaming are deliberately unsupported.
    """

    def __init__(self, model: str, openai_client: AsyncOpenAI, *, context_settings: ContextSettings) -> None:
        super().__init__(model, openai_client)
        self.context_settings = context_settings
        self.last_input_tokens: int | None = None
        if context_settings.reserve <= 0:
            raise ValueError("BudgetedResponsesModel requires a positive output reserve")

    async def _fetch_response(
        self, system_instructions: str | None, input: Any, model_settings: ModelSettings,
        tools: list[Any], output_schema: Any, handoffs: list[Any],
        previous_response_id: str | None = None, conversation_id: str | None = None,
        stream: bool = False, prompt: Any = None,
    ) -> Response:
        if stream or prompt is not None or previous_response_id is not None or conversation_id is not None:
            raise UserError("BudgetedResponsesModel requires non-streaming, explicit input without stored prompts or server history")
        unknown_args = set(model_settings.extra_args or {}) - _NON_CONTEXT_EXTRA_ARGS
        if model_settings.extra_body or unknown_args or model_settings.context_management:
            raise UserError("BudgetedResponsesModel does not support payload overrides or server-side compaction")
        if model_settings.truncation == "auto":
            raise UserError("Automatic truncation would change the counted context")

        reserve = self.context_settings.reserve
        limit = self.context_settings.limit
        if reserve <= 0:
            raise ValueError("BudgetedResponsesModel requires a positive output reserve")
        settings = replace(model_settings, max_tokens=min(model_settings.max_tokens or reserve, reserve))
        # Build once. The exact same payload is counted and generated, even if another
        # task changes a tool definition while the counting request is in flight.
        request = deepcopy(self._build_response_create_kwargs(
            system_instructions, input, settings, tools, output_schema, handoffs,
            previous_response_id=None, conversation_id=None, stream=False, prompt=None,
        ))
        count_request = {key: value for key, value in request.items() if key in _COUNT_FIELDS}
        client = self._get_client()
        count = await client.responses.input_tokens.count(**count_request)
        tokens = count.input_tokens
        if type(tokens) is not int or tokens < 0:
            raise UserError("The token-count endpoint returned an invalid input token count")
        self.last_input_tokens = tokens
        if tokens > limit:
            raise ContextBudgetExceeded(tokens, limit)
        response = await client.responses.create(**request)
        if getattr(response, "status", None) in {"failed", "incomplete"}:
            raise response_terminal_failure_error(f"response.{response.status}", response)
        _mark_transport_request_without_usage(response)
        return response
