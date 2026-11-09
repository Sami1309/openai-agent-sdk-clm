"""An agent that manages its own context while reading noisy tool output.

    OPENAI_API_KEY=... uv run python examples/basic.py
"""

import asyncio

from agents import function_tool

from agents_clm import CLMAgent, CLMRunner, ContextSettings


@function_tool
def read_page(page: int) -> str:
    """Read one page of the server log.

    Args:
        page: Page number, from 1 to 5.
    """
    noise = "\n".join(f"INFO request {page}-{i} completed in 12ms" for i in range(150))
    fact = "ERROR the payments service restarted at 03:14" if page == 4 else "no errors on this page"
    return f"{noise}\n{fact}"


async def main() -> None:
    agent = CLMAgent(
        name="Log reader",
        model="gpt-5.4-mini",
        instructions="Read pages 1 to 5 of the log, one at a time, then report any errors.",
        tools=[read_page],
        context_settings=ContextSettings(
            budget=6_000,
            reserve=512,
            skill="After each page, use one command to replace that page's result with a one-line note.",
        ),
    )
    result = await CLMRunner.run(agent, "What went wrong?", max_turns=25)

    print(result.final_output)
    summary = agent.live.trace.summary()
    print(f"Peak context {summary['peak_context']} tokens, {summary['edits_applied']} edits applied.")


if __name__ == "__main__":
    asyncio.run(main())
