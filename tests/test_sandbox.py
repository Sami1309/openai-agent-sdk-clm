"""The ContextFile capability on a real SDK sandbox session (the local Unix backend)."""

import json

from agents import RunConfig
from agents.sandbox import SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from agents.sandbox.sandboxes import UnixLocalSandboxClient

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
