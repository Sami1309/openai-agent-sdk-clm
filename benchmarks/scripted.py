"""A fake SDK ``Model`` so the real Runner loop can be tested without an API key."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agents import Model, ModelResponse, Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText


def call(name: str, arguments: str, call_id: str) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(type="function_call", name=name, arguments=arguments, call_id=call_id)


def message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


class ScriptedModel(Model):
    """Replays a list of outputs, or calls a policy with each prompt."""

    def __init__(self, script: list[Any] | Callable[[str | None, list[Any]], list[Any]]) -> None:
        self.script = script
        self.prompts: list[tuple[str | None, list[Any]]] = []

    async def get_response(self, system_instructions: str | None, input: Any, *args: Any, **kwargs: Any) -> ModelResponse:
        self.prompts.append((system_instructions, list(input)))
        if callable(self.script):
            output = self.script(system_instructions, list(input))
        else:
            output = self.script[len(self.prompts) - 1]
        return ModelResponse(output=output, usage=Usage(requests=1, input_tokens=1, output_tokens=1, total_tokens=2), response_id=None)

    def stream_response(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


def needle_policy(method: str) -> Callable[[str | None, list[Any]], list[Any]]:
    """Hard-coded play of needle retention. Proves the plumbing and says nothing about model skill."""
    keep_only_needles = (
        "python3 - <<'PY' && echo READY_FOR_NEXT_OP\n"
        "import re\n"
        "p = '.live_ctx/LIVE_CTX_MAIN.txt'\n"
        "needles = re.findall(r'^\\[n\\d+i\\d+#\\w+\\] .*$', open(p).read(), re.M)\n"
        "open(p, 'w').write('[[CTX_TURN 1 role=notes]]\\n' + '\\n'.join(needles))\n"
        "PY"
    )
    command = keep_only_needles if method == "clm" else "echo READY_FOR_NEXT_OP"
    counter = {"n": 0}

    def policy(_: str | None, items: list[Any]) -> list[Any]:
        counter["n"] += 1
        return [call("bash", json.dumps({"command": command}), f"call_{counter['n']}")]

    return policy
