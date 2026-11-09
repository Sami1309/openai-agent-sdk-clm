"""Recover real conversations without replaying completed tool calls."""

import json

import pytest
from agents import MaxTurnsExceeded, RunConfig, UserError, function_tool

from agents_clm import CLMAgent, CLMRunner, LiveContext, LocalContextStore
from benchmarks.scripted import ScriptedModel, call, message


def make_agent(tmp_path, model, **kwargs):
    live = LiveContext(store=LocalContextStore.in_workdir(tmp_path))
    return CLMAgent(name="a", live=live, model=model, **kwargs)


async def test_checkpoint_restores_protected_task_and_real_tool_history(tmp_path):
    executions = []

    @function_tool
    def lookup() -> str:
        """Return a fact."""
        executions.append(True)
        return "a useful fact"

    checkpoint = tmp_path / "trusted" / "conversation.json"
    first = make_agent(tmp_path / "first", ScriptedModel([[call("lookup", "{}", "c1")], [message("one")]]), tools=[lookup])
    await CLMRunner.run(first, "protected task", checkpoint=checkpoint, run_config={"tracing_disabled": True})
    assert checkpoint.stat().st_mode & 0o777 == 0o600

    model = ScriptedModel([[message("two")]])
    restored = make_agent(tmp_path / "second", model, tools=[lookup])
    await restored.live.restore_checkpoint(checkpoint)
    await CLMRunner.run(restored, "continue", run_config={"tracing_disabled": True})
    items = model.prompts[0][1]
    assert items[0] == {"role": "user", "content": "protected task"}
    assert any(i.get("type") == "function_call" and i["call_id"] == "c1" for i in items)
    assert any(i.get("type") == "function_call_output" and "a useful fact" in i["output"] for i in items)
    assert any(i.get("content") == "one" for i in items)
    assert len(executions) == 1


async def test_checkpoint_includes_unsynced_edits_and_keeps_them_after_restart(tmp_path):
    agent = make_agent(tmp_path / "first", ScriptedModel([[message("discard this")]]))
    await CLMRunner.run(agent, "task", run_config={"tracing_disabled": True})
    await agent.live.store.write("[[CTX_TURN 1 role=notes]]\nremember this instead")
    checkpoint = tmp_path / "checkpoint.json"
    await agent.live.save_checkpoint(checkpoint)
    restored = make_agent(tmp_path / "second", ScriptedModel([]))
    await restored.live.restore_checkpoint(checkpoint)
    assert restored.live.protected[0].text == "task"
    assert "remember this instead" in await restored.live.read()
    assert "discard this" not in await restored.live.read()


@pytest.mark.parametrize("damage", ["json", "version", "format", "turn", "file"])
async def test_invalid_checkpoint_leaves_existing_state_and_file_untouched(tmp_path, damage):
    agent = make_agent(tmp_path / "workspace", ScriptedModel([[message("kept")]]))
    await CLMRunner.run(agent, "task", run_config={"tracing_disabled": True})
    path = tmp_path / "state.json"
    await agent.live.save_checkpoint(path)
    before = await agent.live.read()
    state = json.loads(path.read_text())
    if damage == "version":
        state["version"] = 99
    elif damage == "format":
        state["format"] = "unknown.Format"
    elif damage == "turn":
        state["turns"][0]["raw"] = {"type": "function_call"}
    elif damage == "file":
        state["file"] = "corrupted"
    path.write_text("{" if damage == "json" else json.dumps(state))
    with pytest.raises(UserError, match="checkpoint"):
        await agent.live.restore_checkpoint(path)
    assert await agent.live.read() == before
    assert agent.live.protected[0].text == "task"


async def test_failed_checkpoint_replace_keeps_previous_checkpoint(tmp_path, monkeypatch):
    import os

    agent = make_agent(tmp_path / "workspace", ScriptedModel([[message("one")], [message("two")]]))
    path = tmp_path / "state.json"
    await CLMRunner.run(agent, "task", checkpoint=path, run_config={"tracing_disabled": True})
    original = path.read_bytes()
    await CLMRunner.run(agent, "next", run_config={"tracing_disabled": True})
    replace = os.replace

    def fail_checkpoint(src, dst, **kwargs):
        if dst == path.name:
            raise OSError("simulated disk failure")
        return replace(src, dst, **kwargs)

    monkeypatch.setattr(os, "replace", fail_checkpoint)
    with pytest.raises(OSError):
        await agent.live.save_checkpoint(path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".context-*.tmp"))


async def test_checkpoint_operations_reject_active_run(tmp_path):
    agent = make_agent(tmp_path, ScriptedModel([]))
    with agent.live.run_scope():
        with pytest.raises(UserError, match="already running"):
            await agent.live.save_checkpoint(tmp_path / "state.json")
        with pytest.raises(UserError, match="already running"):
            await agent.live.restore_checkpoint(tmp_path / "state.json")


@pytest.mark.parametrize("alias", [False, True])
async def test_checkpoint_cannot_overwrite_editable_context(tmp_path, alias):
    agent = make_agent(tmp_path, ScriptedModel([[message("kept")]]))
    await CLMRunner.run(agent, "task", run_config={"tracing_disabled": True})
    path = agent.live.store.path
    before = await agent.live.read()
    if alias:
        path = path.parent / "unused" / ".." / path.name
    with pytest.raises(UserError, match="separate"):
        await agent.live.save_checkpoint(path)
    assert await agent.live.read() == before


async def test_max_turns_checkpoint_includes_completed_output(tmp_path):
    @function_tool
    def lookup() -> str:
        """Return a completed result."""
        return "completed result"

    agent = make_agent(tmp_path / "first", ScriptedModel([[call("lookup", "{}", "c1")]]), tools=[lookup])
    path = tmp_path / "state.json"
    with pytest.raises(MaxTurnsExceeded):
        await CLMRunner.run(agent, "task", max_turns=1, checkpoint=path, run_config=RunConfig(tracing_disabled=True))
    restored = make_agent(tmp_path / "second", ScriptedModel([]))
    await restored.live.restore_checkpoint(path)
    assert any(i.get("output") == "completed result" for i in restored.live.input_items)
