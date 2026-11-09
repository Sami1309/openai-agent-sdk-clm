# Evaluation results

## Live audit — November 8, 2026

The [machine-readable audit report](results/2026-11-08-live-audit.json) contains run IDs, implementation fingerprints, scores, usage, and exclusions. Full traces remain in local `runs/` directories. These are engineering checks and limited benchmark samples, not a reproduction of the paper.

**SDK validation:** 119 offline tests passed, wheel/source builds succeeded, and all six live integration cases passed on `gpt-5.4-mini`: structured function tools with checkpoint recovery, terminal file edits, image-tool output, assistant phases, schema-budget rejection, and incomplete-response billing. Counted input tokens matched generation usage in the checked successful requests. A separate forced-compaction failure retained all 16 billed output tokens and preserved the previous history.

The live checks found and drove fixes for:

- Lost assistant `phase` metadata during replay and edits.
- Missing usage on failed/incomplete responses, and usage assigned to the wrong turn after a failed request.
- Rejected requests and unsent final snapshots incorrectly contributing to prefix-reuse estimates.
- A summary baseline that discarded commentary containing the actual handoff and retained only the final acknowledgement. It now preserves all summary text, uses dedicated summarizer instructions, and rejects empty handoffs.
- Failed compactions being retried as if the main agent's command had been truncated. They now invalidate the evaluation and retain available billing data.

## Final matched comparison

Run `20261108-202202-pilot`, GPT-5.4, default reasoning, seed 42, needle retention K4-C24. Both methods used the same finished implementation (`bebf7f26522d4a47…`), 32,768-token text budget, and 8,192-token output cap. The generator and grader are ContextBench's; the Summary baseline uses this repository's corrected compaction implementation.

| Method | Score | Operations | Peak context estimate | Model calls | Estimated cost |
|---|---:|---:|---:|---:|---:|
| CLM | 100% | 24/24 | 9,706 | 24 | $0.421 |
| Summary | 100% | 24/24 | 26,967 | 28 | $0.687 |

Both methods retained all needles. This single run shows smaller context and lower cost for CLM; it does not establish a general performance advantage. Costs use provider-reported usage and [GPT-5.4 list prices](https://developers.openai.com/api/docs/models/gpt-5.4), including reported cached input.

## Additional completed checks

The initial live pilot on commit `2773004` completed all four CLM tasks:

| Task | Level | Seed | CLM score | Operations |
|---|---|---:|---:|---:|
| Needle retention | K4-C24 | 42 | 100% | 24/24 |
| KV store | R1000 | 42 | 100% | 34/34 |
| Sudoku sketchpad | t30 | 42 | 100% | 30/30 |
| Log triage | L1600 | 42 | 100% | 139/139 |

CLM also scored 100% on K8-C60 (about 7.5× pressure) for fresh seeds 43 and 44, completing all 60 chunks in each. Seed 43 scored 100% again after the assistant-phase fix. These runs span implementation revisions; their fingerprints are in the audit report.

The corrected Summary baseline completed K4-C24 and Sudoku t30 at 100%. There is **no validated high-pressure Summary comparison** from this audit. Older summary results are excluded because of the extraction defect; one older stress run also received a provider-side prompt rejection. Remaining jobs using superseded failure handling were interrupted. Their incomplete results are not scored as retention failures.

Saved completed benchmark/integration results total about **$17.49 in estimated usage**. This is not the total API bill: interrupted requests, ad hoc probes, and undercounted failures in the earlier implementation are not fully captured. Docker integration was not exercised.

## Reproduce

```bash
# Paid live integration checks; expected to cost a small fraction of a dollar.
uv run --env-file .env python -m benchmarks.integration

# The final matched comparison above.
uv run --env-file .env python -m benchmarks.run --profile pilot \
  --tasks needle_retention --methods clm summary --concurrency 2 --max-usd 3

# A selected higher-pressure level, with independent seeds.
uv run --env-file .env python -m benchmarks.run --profile figure2 \
  --tasks needle_retention --levels K8-C60 --methods clm --seeds 43 44 \
  --concurrency 2 --max-usd 4
```

`--max-usd` stops new runs after the estimated threshold; in-flight runs can exceed it. Models need a known price in `benchmarks.run.PRICES`. `--carry RUN_ID` requires matching model, reasoning, budget, source, and implementation fingerprint; it rejects older reports without a fingerprint. Reports include dependency versions. The final checks used Python 3.12.12, Agents SDK 0.24.0, OpenAI Python 3.46.0, ContextBench 0.1.0, and tiktoken 0.14.0.

## Historical measurements

The following results predate the reliability fixes and summary-baseline audit. Keep them as exploratory records; their Summary comparisons are not validated. See the [README](../README.md) for setup.

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

The historical ladder remains incomplete. Re-evaluate it on the corrected harness; these older reports cannot be carried forward into new runs.

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
