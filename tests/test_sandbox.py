"""The ContextFile capability on a real SDK sandbox session (the local Unix backend)."""

import json
import re

import pytest
from agents import RunConfig
from agents.sandbox import SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from agents.sandbox.sandboxes import UnixLocalSandboxClient
from agents.sandbox.entries import Dir
from agents.sandbox.manifest import Manifest

from agents_clm import CLMRunner, ContextSettings
from agents_clm.sandbox import ContextFile
from benchmarks.scripted import ScriptedModel, call, message


def exec_command(command: str, call_id: str):
    return call("exec_command", json.dumps({"cmd": command}), call_id)


async def test_sandbox_agent_edits_its_context_through_the_sandbox_shell():
    file = ".live_ctx/LIVE_CTX_MAIN.txt"
    wipe_and_note = f"printf '[[CTX_TURN 1 role=notes]]\\nonly this survives' > {file}"
    model = ScriptedModel(
        [
            [exec_command("echo noisy output to forget", "c1")],
            [exec_command(wipe_and_note, "c2")],
            [message("done")],
        ]
    )
    capability = ContextFile(settings=ContextSettings(budget=32_768))
    agent = SandboxAgent(name="a", instructions="sys", model=model, capabilities=[Shell(), capability])
    config = RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient()), tracing_disabled=True)

    result = await CLMRunner.run(agent, "the task", run_config=config, max_turns=5)

    assert result.final_output == "done"
    assert file in model.prompts[0][0]
    third = json.dumps(model.prompts[2][1])
    assert "only this survives" in third and "noisy output to forget" not in third
    assert model.prompts[2][1][0] == {"role": "user", "content": "the task"}
    assert any((s.get("edit") or {}).get("status") == "applied" for s in capability.live.trace.steps)


async def test_context_is_captured_before_sandbox_cleanup_and_uses_model_cwd():
    class StrictClient(UnixLocalSandboxClient):
        """Simulate remote storage becoming unavailable once the sandbox is deleted."""

        async def create(self, **kwargs):
            session = await super().create(**kwargs)
            read, write = session.read, session.write
            session.deleted_for_test = False

            async def checked_read(*args, **kwargs):
                assert not session.deleted_for_test, "read after sandbox deletion"
                return await read(*args, **kwargs)

            async def checked_write(*args, **kwargs):
                assert not session.deleted_for_test, "write after sandbox deletion"
                return await write(*args, **kwargs)

            session.read, session.write = checked_read, checked_write
            return session

        async def delete(self, session):
            result = await super().delete(session)
            session.deleted_for_test = True
            return result

    def edit(instructions, _):
        path = re.search(r"mirrored to `([^`]+)`", instructions).group(1)
        return [exec_command(f"printf '[[CTX_TURN 1 role=notes]]\\nFINAL SANDBOX EDIT' > '{path}'", "c1")]

    capability = ContextFile()
    agent = SandboxAgent(
        name="a", model=ScriptedModel(edit), capabilities=[Shell(), capability],
        tool_use_behavior="stop_on_first_tool",
    )
    config = RunConfig(
        sandbox=SandboxRunConfig(client=StrictClient(), cwd="project", manifest=Manifest(entries={"project": Dir()})),
        tracing_disabled=True,
    )
    await CLMRunner.run(agent, "task", run_config=config)
    assert any(t.role == "notes" and t.text == "FINAL SANDBOX EDIT" for t in capability.live.turns)
    assert "FINAL SANDBOX EDIT" in await capability.live.read()


@pytest.mark.parametrize("path", ["", ".", "../ctx", "/tmp/ctx", "a/../ctx", "a\\ctx"])
def test_context_capability_requires_workspace_relative_path(path):
    with pytest.raises(ValueError):
        ContextFile(path=path)
