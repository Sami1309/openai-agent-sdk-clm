# openai-agents-clm

Lets an [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) agent be its own [Context Language Model](https://arxiv.org/abs/2609.37725), instead of using the SDK's append-only context. See [GOAL.md](GOAL.md).

The agent's live context is a file. The agent edits that file with ordinary tools, and its next model call sends whatever the file now says.

```python
from agents_clm import CLMAgent, CLMRunner, ContextSettings

agent = CLMAgent(
    name="Researcher",
    instructions="...",
    tools=[...],
    context_settings=ContextSettings(budget=32_768),
)
result = await CLMRunner.run(agent, "Your task", max_turns=100)

await agent.live.read()       # the context file as the agent left it
agent.live.trace.summary()    # peak context, prefix reuse, reference cost
```

`CLMAgent` is an ordinary SDK `Agent`, so tools, models, and hooks work as usual. Run the same agent again to continue a conversation with its live context.

## Quick start

```bash
uv sync
uv run python -m pytest                      # no API key needed
uv run python -m benchmarks.run --scripted   # offline demo with a fake model
uv run python -m dashboard                   # http://127.0.0.1:8765
```

## Three ways to use it

The package follows the SDK's own conventions, so use whichever level fits.

| Level | How | Example |
|---|---|---|
| Agent | `CLMAgent` with `CLMRunner` | [`examples/basic.py`](examples/basic.py) |
| Stock `Agent` and `Runner` | Pass `LiveContext` as `RunConfig.call_model_input_filter`, the same hook as the SDK's `ToolOutputTrimmer` | [`examples/stock_runner.py`](examples/stock_runner.py) |
| SDK sandbox | Add the `ContextFile` capability to a `SandboxAgent`, on Docker or any other backend | [`examples/sandbox_agent.py`](examples/sandbox_agent.py) |

With a stock `Runner`, call `live.begin_run()` before each run and `await live.finish(result)` after it, if you continue a conversation across runs. `CLMRunner` does this for you.

## How it works

The SDK calls `call_model_input_filter` immediately before every model request. `LiveContext` is that filter:

1. **Mirror.** Turns are written to `LIVE_CTX_MAIN.txt`, one `[[CTX_TURN n role=x]]` block each.
2. **Act.** The agent runs a shell command, an ordinary tool call, and can rewrite the file however it wants.
3. **Sync.** The filter reads the file back, re-pins the original task, and appends the newest turns.
4. **Send.** The request is built from the file, not from the runner's append-only list.

Past tool calls stay real tool calls even when the agent edits their results, because a model shown its history as plain text starts writing tool calls as plain text. Header-like lines inside a turn are escaped, so tool output can't forge a turn.

## Changing how it behaves

| To change | Do this |
|---|---|
| The budget, reminders, or prompt | `ContextSettings(budget=..., warn_near_limit=..., prompt=...)` |
| How the agent should manage context | `ContextSettings(skill="...")`, in-context steering from paper Eq. 4 |
| The policy itself | Subclass `ContextManager` and override `update`, as in [`examples/custom_policy.py`](examples/custom_policy.py) |
| The file's format | Subclass `ContextFileFormat` and pass `LiveContext(file_format=...)` |
| Where the file lives | Implement `ContextStore` (`read`, `write`, `location`) |
| The tool that edits it | Add your own tool named `bash` to `CLMAgent`, or use any SDK sandbox shell |

| SDK concept | This package |
|---|---|
| `agents/agent.py`: `Agent`, `SandboxAgent` | `agent.py`: `CLMAgent` |
| `agents/run.py`: `Runner` | `run.py`: `CLMRunner` |
| `ModelSettings` | `settings.py`: `ContextSettings` |
| `ToolOutputTrimmer`, a filter object | `context_manager.py`, `live_context.py` |
| `sandbox.capabilities.Capability` | `sandbox.py`: `ContextFile` |
| `agents/exceptions.py` | `exceptions.py`: `ContextBudgetExceeded` |

## Results

These use the paper's [ContextBench](https://github.com/RulinShao/ContextBench): its official generators, graders, level definitions, and method skills, with GPT-5.4 and the paper's 32K limit. Scores are the share of the task graded correct from the agent's own context.

| Task | Level | Pressure | Base | Summary | CLM |
|---|---|---|---|---|---|
| Needle retention | K4-C8 | 1.0× | 100% | 100% | **100%** |
| | K4-C24 | 3.0× | 33% | 100% | **100%** |
| | K8-C60 | 7.5× | 13% | not run | **100%** |
| | K2-C192 | 23× | 4% | not run | not run |
| KV store | R520 | 0.85× | 0% | invalid | **100%** |
| | R1000 | 1.6× | 0% | not run | **100%** |
| | R4000 | 6.0× | 0% | not run | **100%** |
| | R16000 | 24× | 0% | not run | not run |
| Sudoku sketchpad | t15 | 0.89× | 60% | 100% | **100%** |
| | t30 | 1.7× | 30% | 100% | **100%** |
| | t60 | 3.2× | 15% | not run | not run |
| | t100 | 5.3× | 9% | not run | not run |
| Log triage | L640 | 0.93× | 0% | not run | not run |
| | L1600 | 2.2× | 0% | 92% | **100%** |
| | L3200 | 4.1× | 0% | not run | not run |

- **CLM scored 100% on all 9 levels it finished, up to 7.5× pressure.** That matches paper Figure 2, where CLM holds near 100% as the baselines fall away.
- **CLM kept its context far smaller:** 7.5K to 21.5K tokens at peak, against 25K to 27K for Summary.
- **CLM used 23% to 67% less compute than Summary** on the 5 levels both finished, measured in reference PFLOPs.

Read these with care:

- **It's one seed per level.** The paper uses four or more.
- **The ladder is incomplete.** The API account ran out of credits partway through. "Not run" means the run stopped on that error or never started, so the comparison at the highest pressures, which is the paper's strongest claim, is not yet shown.
- **Summary is not yet shown failing.** It scored 92% to 100% on the 5 levels it finished, all at 3× pressure or below. The paper's baselines fall away at higher pressure than Summary reached here.
- **KV R520 Summary is invalid.** A harness bug, now fixed, passed tool calls to the summarizer as plain text and corrupted a compaction.
- **Base's 0% on KV reflects its skill.** The official skill suggests copying values to disk by retyping them. GPT-5.4 did this, doubled its context, and hit the limit before any query.

To finish the ladder, add API credits and run this, which reuses every valid result and costs roughly $40 to $50:

```bash
export OPENAI_API_KEY=sk-...
uv run python -m benchmarks.run --profile figure2 --carry 20261108-150104-figure2 --max-usd 50
```

The paper's other results (BrowseComp-Plus, TerminalBench, EdgeBench, swarms) need self-hosted models and multi-hour container runs and are out of scope here.

Reference PFLOPs apply the paper's Qwen3.6-27B constants (Eq. 9) to each run's token trace, because OpenAI's architectures aren't public. Treat them as a common yardstick and not as real compute. Costs are estimates from [list prices](https://developers.openai.com/api/docs/models/gpt-5.4).

## Relation to the paper

| Implemented | Not implemented |
|---|---|
| Context as a file, Eq. 2 | Suffix Cache Reuse (needs server control) |
| Append by default, protected system prompt and task | Reinforcement learning (needs model weights) |
| In-context steering, Eq. 4 | Skill evolution loop |
| Size readouts, reminders, edit gating | Subagents and multiple context files |
| Prefix-reuse cost, Eqs. 3 and 9 | Rollback and retry at the limit (the run ends) |

Differences from the paper's benchmark setup:

- The CLM harness and system prompt are this package's own.
- Skills are unmodified, except that `/tmp/` paths point at each run's workspace.
- Only two of the paper's six baselines are included: Base and Summary.
- The Summary baseline's prompts are based on Codex's, reconstructed from the text the official skills quote.
- At the budget limit the run ends at once, with no final turn.

## Limitations

- Not supported: `session`, `conversation_id`, and `previous_response_id`, which keep context outside the agent's control, and streaming.
- Handoffs: only the `CLMAgent` itself manages its context.
- Reasoning items are not kept in the live context, since they are opaque to the model.
- `result.to_input_list()` still returns the SDK's full transcript. Use `agent.live.input_items` for the live context.

## Safety

- `CLMAgent`'s default `bash` tool runs commands written by the model. On macOS it uses `sandbox-exec`: no network, writes only inside a temporary workspace, no reads from your home directory, and no API keys in its environment. On other platforms it refuses to run unless you pass `allow_unsandboxed=True`, which you should only do inside a container. For stronger isolation, use the `ContextFile` capability on a Docker sandbox.
- As the paper warns, an editable context can let a prompt injection persist across turns.

## Licenses

ContextBench's skills and level definitions in `benchmarks/contextbench_assets/` are Apache-2.0. The authors' [reference code](https://github.com/facebookresearch/context-language-models) is CC BY-NC 4.0. This project is an independent implementation that keeps the same `[[CTX_TURN]]` file format.
