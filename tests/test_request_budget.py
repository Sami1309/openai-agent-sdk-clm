"""Exercise real SDK request serialization against an offline HTTP transport."""

import json

import httpx2
import pytest
from agents import AgentOutputSchema, ModelSettings, UserError, function_tool
from agents.models.interface import ModelTracing
from openai import AsyncOpenAI, InternalServerError
from pydantic import BaseModel

from agents_clm import BudgetedResponsesModel, CLMAgent, CLMRunner, ContextBudgetExceeded, ContextSettings


@function_tool
def lookup(term: str) -> str:
    """Look up a term in a dictionary."""
    return term


class Answer(BaseModel):
    answer: str


def make_model(settings, *, count=100, fail_count=False, mutate=None):
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("/input_tokens"):
            if mutate:
                mutate()
            if fail_count:
                return httpx2.Response(500, json={"error": {"message": "counter unavailable", "type": "server_error"}})
            return httpx2.Response(200, json={"object": "response.input_tokens", "input_tokens": count})
        return httpx2.Response(200, json={
            "id": "resp_1", "object": "response", "created_at": 1, "model": "gpt-5.4-mini",
            "status": "completed", "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
            "output": [{"id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": '{"answer":"ok"}', "annotations": []}]}],
            "usage": {"input_tokens": count, "output_tokens": 8, "total_tokens": count + 8,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
        })

    client = AsyncOpenAI(api_key="test-key", max_retries=0, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    model = BudgetedResponsesModel("gpt-5.4-mini", client, context_settings=settings)
    return model, client, requests


async def invoke(model, *, model_settings=None, **kwargs):
    return await model.get_response(
        "system instructions", [{"role": "user", "content": [
            {"type": "input_text", "text": "describe this"},
            {"type": "input_image", "image_url": "https://example.com/image.png", "detail": "auto"},
        ]}], model_settings or ModelSettings(max_tokens=500), [lookup], AgentOutputSchema(Answer), [],
        ModelTracing.DISABLED, **kwargs,
    )


async def test_counts_exact_serialized_input_tools_schema_and_media_before_generation():
    settings = ContextSettings(budget=1000, reserve=200)
    model, client, requests = make_model(settings)
    async with client:
        await invoke(model)
    assert [path for path, _ in requests] == ["/v1/responses/input_tokens", "/v1/responses"]
    counted, sent = requests[0][1], requests[1][1]
    assert all(sent[key] == value for key, value in counted.items())
    assert counted["tools"][0]["name"] == "lookup"
    assert counted["text"]["format"]["schema"]["properties"]["answer"]["type"] == "string"
    assert counted["input"][0]["content"][1]["type"] == "input_image"
    assert sent["max_output_tokens"] == 200
    assert model.last_input_tokens == 100


async def test_in_flight_tool_mutation_cannot_change_the_counted_payload():
    original = lookup.description
    model, client, requests = make_model(ContextSettings(), mutate=lambda: setattr(lookup, "description", "changed"))
    try:
        async with client:
            await invoke(model)
        assert requests[0][1]["tools"] == requests[1][1]["tools"]
        assert requests[1][1]["tools"][0]["description"] == original
    finally:
        lookup.description = original


async def test_over_budget_aborts_before_generation_through_real_runner(tmp_path):
    settings = ContextSettings(budget=2000, reserve=200)
    model, client, requests = make_model(settings, count=1801)
    agent = CLMAgent(name="a", model=model, context_settings=settings, tools=[lookup], output_type=Answer, workdir=tmp_path)
    async with client:
        with pytest.raises(ContextBudgetExceeded) as caught:
            await CLMRunner.run(agent, "task", run_config={"tracing_disabled": True})
    assert caught.value.tokens == 1801 and caught.value.limit == 1800
    assert len(requests) == 1
    assert agent.live.trace.summary()["model_calls"] == 0
    assert agent.live.trace.steps[-1]["provider_input_tokens"] == 1801


async def test_count_failure_never_falls_back_to_estimation():
    model, client, requests = make_model(ContextSettings(), fail_count=True)
    async with client:
        with pytest.raises(InternalServerError):
            await invoke(model)
    assert len(requests) == 1


async def test_successful_structured_response_through_real_runner(tmp_path):
    settings = ContextSettings(budget=2000, reserve=200)
    model, client, requests = make_model(settings)
    agent = CLMAgent(name="a", model=model, context_settings=settings, output_type=Answer, workdir=tmp_path)
    async with client:
        result = await CLMRunner.run(agent, "task", run_config={"tracing_disabled": True})
    assert result.final_output == Answer(answer="ok")
    assert result.context_wrapper.usage.input_tokens == 100
    assert len(requests) == 2
    assert requests[0][1]["input"] == requests[1][1]["input"]
    assert agent.live.input_items[-1]["content"] == '{"answer":"ok"}'


@pytest.mark.parametrize("kwargs", [{"prompt": {"id": "p"}}, {"previous_response_id": "r"}, {"conversation_id": "c"}])
async def test_uninspectable_server_context_is_rejected(kwargs):
    model, client, requests = make_model(ContextSettings())
    async with client:
        with pytest.raises(UserError):
            await invoke(model, **kwargs)
    assert not requests


@pytest.mark.parametrize("settings", [
    ModelSettings(extra_body={"input": "override"}),
    ModelSettings(extra_args={"model": "other"}),
    ModelSettings(truncation="auto"),
    ModelSettings(context_management=[{"type": "compaction"}]),
])
async def test_payload_overrides_and_automatic_context_changes_are_rejected(settings):
    model, client, requests = make_model(ContextSettings())
    async with client:
        with pytest.raises(UserError):
            await invoke(model, model_settings=settings)
    assert not requests


async def test_smaller_explicit_output_limit_is_preserved_and_exact_boundary_allowed():
    model, client, requests = make_model(ContextSettings(budget=1000, reserve=200), count=800)
    async with client:
        await invoke(model, model_settings=ModelSettings(max_tokens=50))
    assert requests[1][1]["max_output_tokens"] == 50
