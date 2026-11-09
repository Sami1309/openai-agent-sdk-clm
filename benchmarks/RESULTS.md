# Benchmark results

Historical results from the initial implementation, before the reliability fixes. They have not been rerun against the current code. These are exploratory measurements, not a validated comparison. See the [README](../README.md) for setup.

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

- **CLM scored 100% on all 9 levels it finished, up to 7.5× pressure.** The incomplete, single-seed runs do not establish a reproduction of paper Figure 2.
- **CLM kept its context far smaller:** 7.5K to 21.5K tokens at peak, against 25K to 27K for Summary.
- **CLM used 23% to 67% less compute than Summary** on the 5 levels both finished, measured in reference PFLOPs.

Read these with care:

- **It's one seed per level.** The paper uses four or more.
- **The ladder is incomplete.** The API account ran out of credits partway through. "Not run" means the run stopped on that error or never started, so the comparison at the highest pressures, which is the paper's strongest claim, is not yet shown.
- **Summary is not yet shown failing.** It scored 92% to 100% on the 5 levels it finished, all at 3× pressure or below. The paper's baselines fall away at higher pressure than Summary reached here.
- **KV R520 Summary is invalid.** A harness bug, now fixed, passed tool calls to the summarizer as plain text and corrupted a compaction.
- **Base's 0% on KV reflects its skill.** The official skill suggests copying values to disk by retyping them. GPT-5.4 did this, doubled its context, and hit the limit before any query.

To continue the recorded ladder, set `OPENAI_API_KEY` and run the command below. It requires the original run artifacts under `runs/`; `--max-usd` is an estimated spending guard, not a provider-side cap. Carry-forward now requires matching source, model, reasoning, and budget settings.

```bash
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
