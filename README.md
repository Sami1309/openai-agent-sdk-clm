# openai-agents-clm

An [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) extension that lets an agent manage its own context. The agent edits a text file with ordinary tools; each model request uses that file's contents, with the original task protected.

Inspired by [Context Language Models](https://arxiv.org/abs/2609.37725). Targets **`openai-agents` 0.24.x**. See [GOAL.md](GOAL.md) for the project's scope.

## Quick start

From this checkout:

```bash
uv sync
uv run python -m pytest                     # offline tests
uv run python -m benchmarks.run --scripted  # offline demo
```

Set `OPENAI_API_KEY` to run a real model. The default shell uses macOS `sandbox-exec`; on other POSIX systems, use an [SDK sandbox](examples/sandbox_agent.py), or run inside a container with `allow_unsandboxed=True`.

```python
import asyncio
from agents_clm import CLMAgent, CLMRunner, ContextSettings

async def main():
    agent = CLMAgent(
        name="Researcher",
        model="gpt-5.4-mini",
        instructions="Use bash to investigate. Keep useful findings in your context file.",
        context_settings=ContextSettings(budget=32_768, reserve=2_048),
    )
    result = await CLMRunner.run(agent, "Compute the sum of the integers 1 through 100.")
    print(result.final_output)

    # Continue with only the new input; the live context persists.
    result = await CLMRunner.run(agent, "Now include 101 through 200.")
    print(result.final_output)

asyncio.run(main())
```

## How it works

1. `LiveContext` writes conversation turns to `.live_ctx/LIVE_CTX_MAIN.txt`.
2. The agent edits that file through `bash` or another tool.
3. Before the next request, the SDK input filter reads the edits and appends new turns.
4. The original task stays protected, and unchanged function calls retain their SDK structure.

Final tool edits and completed results at `max_turns` are retained. Inspect the active history with `agent.live.input_items`, the file with `await agent.live.read()`, and estimates with `agent.live.trace.summary()`. The SDK result still contains its full transcript.

## Integration and configuration

| Need | Use |
|---|---|
| Default agent and shell | [`CLMAgent` + `CLMRunner`](examples/basic.py) |
| Existing SDK agent | [`LiveContext` as an input filter](examples/stock_runner.py) |
| Docker or another SDK sandbox | [`ContextFile` capability](examples/sandbox_agent.py) |
| Different context policy | [Subclass `ContextManager`](examples/custom_policy.py) |
| Resume a conversation after restart | [Trusted checkpoints](docs/usage.md#checkpoints) |
| Count the full Responses request | [`BudgetedResponsesModel`](docs/usage.md#request-budgets) |

`ContextSettings` controls the budget, output reserve, protected input count, reminders, instructions, and file-size cap. Implement `ContextStore` or subclass `ContextFileFormat` to change storage or formatting.

## Limits and safety

- Use a separate agent and workspace per conversation. Concurrent runs sharing a live context are rejected; separate processes need application-level coordination.
- Handoffs, streaming, SDK sessions, server-managed history, and approval/`RunState` resumption are unsupported. Use messages and function tools; unsupported history items are rejected.
- The default budget estimates text tokens. For schemas, framing, and media, opt into `BudgetedResponsesModel`; it adds a token-count API call and caps output at the reserve.
- The context file defaults to an 8 MiB limit. Local storage rejects symlink traversal and hard-linked reads, and uses atomic writes. Shell output is bounded; timeouts and cancellations terminate the process group.
- Model-written commands still require isolation. The macOS shell blocks network access and home-directory reads outside its workspace. Use a container for stronger isolation. Editable context can preserve prompt injections.

See [usage and compatibility](docs/usage.md) for checkpoint guarantees and detailed limits.

## Benchmarks and provenance

[Historical ContextBench results](benchmarks/RESULTS.md) are incomplete, single-seed measurements from the initial implementation. They have not been rerun after the reliability fixes. View local runs with `uv run python -m dashboard` at `http://127.0.0.1:8765`.

ContextBench's bundled skills and level definitions are Apache-2.0. The authors' [reference implementation](https://github.com/facebookresearch/context-language-models) is CC BY-NC 4.0. This is an independent implementation using the same `[[CTX_TURN]]` file format.
