"""Write your own fixed context policy by overriding ``ContextManager.update``.

This one keeps only the two most recent tool results in full. ``ContextManager`` provides the
token budget and the per-call trace.

    OPENAI_API_KEY=... uv run python examples/custom_policy.py
"""

import asyncio

from agents import Agent, RunConfig, Runner, function_tool
from agents.run_config import ModelInputData

from agents_clm import ContextManager


class KeepRecentToolResults(ContextManager):
    async def update(self, model_data: ModelInputData, new: list[dict]) -> ModelInputData:
        self.view.extend(new)
        outputs = [i for i in self.view if i.get("type") == "function_call_output"]
        for item in outputs[:-2]:
            item["output"] = "(old result removed)"
        return ModelInputData(input=list(self.view), instructions=model_data.instructions)


@function_tool
def fetch(n: int) -> str:
    """Fetch record n.

    Args:
        n: Record number.
    """
    return f"record {n}: " + "x" * 2000


async def main() -> None:
    manager = KeepRecentToolResults()
    agent = Agent(name="Fetcher", model="gpt-5.4-mini", instructions="Fetch records one at a time.", tools=[fetch])
    result = await Runner.run(
        agent,
        "Fetch records 1, 2, 3, and 4, then say how many you fetched.",
        run_config=RunConfig(call_model_input_filter=manager),
        max_turns=10,
    )
    print(result.final_output)
    print(manager.trace.summary())


if __name__ == "__main__":
    asyncio.run(main())
