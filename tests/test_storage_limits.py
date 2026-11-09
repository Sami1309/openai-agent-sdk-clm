"""Byte limits apply before parsing, including model edits and sandbox cleanup."""

import io

import pytest
from agents.run_config import CallModelData, ModelInputData

from agents_clm import CLMAgent, ContextFileTooLarge, ContextSettings, LiveContext, LocalContextStore
from agents_clm.sandbox import SandboxContextStore


async def test_local_read_and_write_are_bounded_in_bytes(tmp_path):
    store = LocalContextStore.in_workdir(tmp_path, max_bytes=4)
    await store.write("éé")
    with pytest.raises(ContextFileTooLarge):
        await store.write("ééé")
    assert await store.read() == "éé"
    store.path.write_bytes(b"x" * 100)
    with pytest.raises(ContextFileTooLarge):
        await store.read()


async def test_oversized_model_edit_is_rejected_and_repaired(tmp_path):
    store = LocalContextStore.in_workdir(tmp_path, max_bytes=1024)
    live = LiveContext(ContextSettings(prompt=""), store=store)
    agent = CLMAgent(name="a", live=live)
    first = [{"role": "user", "content": "task"}, {"role": "assistant", "content": "keep this"}]
    await live(CallModelData(model_data=ModelInputData(input=first, instructions=""), agent=agent, context=None))
    store.path.write_bytes(b"x" * 1025)
    call = {"type": "function_call", "call_id": "c1", "name": "edit", "arguments": "{}"}
    output = {"type": "function_call_output", "call_id": "c1", "output": "ok"}
    result = await live(CallModelData(model_data=ModelInputData(input=[*first, call, output], instructions=""), agent=agent, context=None))
    assert any(i.get("content") == "keep this" for i in result.input)
    assert "edit REJECTED" in result.input[-1]["output"]
    assert len(store.path.read_bytes()) < 1024


async def test_sandbox_read_uses_bounded_api_and_preserves_error_after_detach():
    class Session:
        async def read_bounded(self, path, *, max_bytes):
            assert max_bytes == 5
            return b"xxxxx"

        async def write(self, *args, **kwargs):
            pass

    store = SandboxContextStore(Session(), "context.txt", max_bytes=4)
    await store.detach()
    with pytest.raises(ContextFileTooLarge):
        await store.read()
    await store.write("ok")
    assert await store.read() == "ok"


async def test_sandbox_user_override_is_not_dropped():
    from agents.sandbox.types import User

    user = User(name="worker")

    class Session:
        async def read(self, path, **kwargs):
            assert kwargs["user"] is user
            return io.BytesIO(b"xxxxx")

    store = SandboxContextStore(Session(), "context.txt", max_bytes=4)
    store.user = user
    with pytest.raises(ContextFileTooLarge):
        await store.read()
