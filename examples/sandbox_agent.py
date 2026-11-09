"""CLM on an SDK sandbox: the context file lives in the sandbox workspace.

Swap ``UnixLocalSandboxClient`` for any other SDK sandbox client, such as Docker, to run the
agent's commands in isolation. The local client does not isolate them.

    OPENAI_API_KEY=... uv run python examples/sandbox_agent.py
"""

import asyncio

from agents import RunConfig
from agents.sandbox import SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from agents.sandbox.sandboxes import UnixLocalSandboxClient

from agents_clm import CLMRunner, ContextSettings
from agents_clm.sandbox import ContextFile


async def main() -> None:
    context_file = ContextFile(settings=ContextSettings(budget=8_000, reserve=512))
    agent = SandboxAgent(
        name="Workspace assistant",
        model="gpt-5.4-mini",
        instructions="Use the shell to answer. Remove long outputs from your context file once you are done with them.",
        capabilities=[Shell(), context_file],
    )
    result = await CLMRunner.run(
        agent,
        "Run `seq 1 400`, then tell me the last number it printed.",
        run_config=RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient())),
        max_turns=10,
    )
    print(result.final_output)
    print(context_file.live.trace.summary())


if __name__ == "__main__":
    asyncio.run(main())
