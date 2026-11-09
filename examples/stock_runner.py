"""CLM with no CLM classes in the run: a plain Agent, Runner, and the SDK's input filter hook.

``LiveContext`` is passed to ``RunConfig.call_model_input_filter``, the same way the SDK's own
``ToolOutputTrimmer`` is.

    OPENAI_API_KEY=... uv run python examples/stock_runner.py
"""

import asyncio
import tempfile

from agents import Agent, RunConfig, Runner

from agents_clm import LiveContext, LocalContextStore, LocalShell


async def main() -> None:
    workdir = tempfile.mkdtemp(prefix="clm_")
    live = LiveContext(store=LocalContextStore.in_workdir(workdir))
    agent = Agent(
        name="Assistant",
        model="gpt-5.4-mini",
        instructions="Use bash to answer. When you are done with a long output, remove it from your context file.",
        tools=[LocalShell(workdir).tool()],
    )
    result = await Runner.run(
        agent,
        "Print the numbers 1 to 300, then tell me the sum of the first and last.",
        run_config=RunConfig(call_model_input_filter=live),
        max_turns=10,
    )
    print(result.final_output)
    print(await live.read())


if __name__ == "__main__":
    asyncio.run(main())
