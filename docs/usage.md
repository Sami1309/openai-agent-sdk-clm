# Usage and compatibility

The extension targets `openai-agents>=0.24,<0.25`. Start with the [README](../README.md) or the [examples](../examples).

## Request budgets

`ContextSettings(budget=32_768, reserve=2_048)` gives the input a limit of 30,720 tokens. The default filter estimates text with `o200k_base`; it excludes API framing, tool and structured-output schemas, and media token costs. It rejects requests above that estimate but does not set the model's output limit.

For Responses API requests, use `BudgetedResponsesModel` with the same settings as the agent:

```python
from openai import AsyncOpenAI
from agents_clm import BudgetedResponsesModel, CLMAgent, CLMRunner, ContextSettings

async def run():
    settings = ContextSettings(budget=32_768, reserve=2_048)
    async with AsyncOpenAI() as client:
        model = BudgetedResponsesModel(
            "gpt-5.4-mini", client, context_settings=settings,
        )
        agent = CLMAgent(name="Assistant", model=model, context_settings=settings)
        result = await CLMRunner.run(agent, "Compute 123 * 456 using bash.")
        print(result.final_output, model.last_input_tokens)
```

This adapter builds the request once, uses OpenAI's [input token-count endpoint](https://developers.openai.com/api/docs/guides/token-counting), and sends the counted payload only if it fits. It includes tools, structured-output schemas, framing, and media. It caps `max_output_tokens` at the reserve, preserving a smaller explicit limit. A positive reserve is required.

Each generation adds a counting round trip. Count errors abort generation; there is no estimate fallback. The provider and model must support the count endpoint. Streaming, stored prompts, server history, automatic truncation/compaction, and payload overrides are rejected. This adapter uses internal SDK request-building hooks; keep the SDK version bound and run the request-parity tests when upgrading.

`ContextBudgetExceeded` ends the run; there is no automatic compaction retry. Trace readouts, prefix reuse, reference compute, and projected costs remain estimates. `model.last_input_tokens` reports the most recent provider count.

The adapter retains provider-reported usage for failed or incomplete Responses requests, including output-limit failures. Rejected preflight requests do not count as generations or prime estimated prefix reuse. For custom drivers, call `manager.begin_run()` before each run and attach usage from that run; usage entries map to completed requests at its start.

`UsageTrackingResponsesModel(model, client)` preserves that failure billing without adding token-count requests or changing output limits. The benchmark runner uses it so failed compactions and interrupted generations remain in cost reports.

## Checkpoints

The editable file alone cannot restore protected inputs or structured tool metadata. Save a separate checkpoint to continue a local agent's conversation after a process restart:

```python
from pathlib import Path
from agents_clm import CLMAgent, CLMRunner

async def run():
    # Keep trusted state outside the model's writable workspace.
    root = Path.home() / ".clm-state"
    root.mkdir(exist_ok=True)
    checkpoint = root.resolve() / "conversation.json"
    agent = CLMAgent(name="Assistant", model="gpt-5.4-mini")

    if checkpoint.exists():
        await agent.live.restore_checkpoint(checkpoint)
    result = await CLMRunner.run(
        agent, "Continue investigating the task.", checkpoint=checkpoint,
    )
    return result.final_output
```

Pass only new input after restoring. Recreate the agent's tools, instructions, model, and policy in application code; checkpoints contain conversation data, not executable configuration. Restore requires the same `ContextFileFormat` class. Trace metrics start fresh.

`CLMRunner` saves after successful completion and after retaining completed outputs from `MaxTurnsExceeded`. Checkpoints use atomic replacement, file/directory synchronization, and a 32 MiB cap. Invalid checkpoints are rejected before replacing the destination context. To save an idle agent explicitly, call `await agent.live.save_checkpoint(path)`.

Only restore trusted, application-owned checkpoints. They include the protected task and raw tool metadata. The model must not be able to edit them. Checkpoints are conversation snapshots, not execution checkpoints: they do not restore sandbox files, resume pending approvals, or provide exactly-once tool execution. A cancellation, provider failure, guardrail failure, or process crash can leave the checkpoint behind completed external side effects. Account for those side effects before retrying.

## SDK integration

`CLMAgent` subclasses `Agent`. `CLMRunner` installs `LiveContext` as `RunConfig.call_model_input_filter` and owns the live context for the duration of the run, including finalization.

With a stock `Runner`, follow [this example](../examples/stock_runner.py): wrap the call in `with live.run_scope():`, pass the filter through `RunConfig`, and call `await live.finish(result)` before leaving that scope. Custom drivers must also handle `MaxTurnsExceeded` finalization and reject unsupported execution modes themselves.

For a `SandboxAgent`, add `ContextFile` alongside the SDK's `Shell` capability and use `CLMRunner`. The context is captured before the SDK destroys the session; subsequent `live.read()` calls use that retained copy. A new sandbox run receives the conversation in its new workspace. Other workspace files are not persisted by this extension.

## Supported history and ownership

- Run the same agent again with only the new input. `result.to_input_list()` is the full SDK transcript; `live.input_items` is the managed context.
- Handoffs are rejected because replaying the source context can undo a handoff's redaction. `session`, `conversation_id`, `previous_response_id`, and enabled `auto_previous_response_id` are also rejected.
- `CLMRunner` does not support streaming or `RunState`/approval resumption. Do not configure approval-dependent tools for it.
- Messages and function calls/results are supported. Opaque reasoning items are dropped. Hosted-tool history items are rejected rather than converted into plain text.
- Structured image/file content remains intact until its turn is explicitly edited into text. Edits cannot forge a new privileged message; existing system/developer messages retain their original roles.
- Assistant `phase` metadata survives replay and in-place text edits, keeping commentary distinct from final answers as recommended in the [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).
- SDK `agent.clone()` is shallow and shares live context and tool instances. Construct independent agents and workspaces for independent conversations. The run lock does not coordinate separate processes or separate contexts pointed at the same file.

## Storage and shell boundaries

The built-in stores default to an 8 MiB UTF-8 file cap, configured by `ContextSettings.max_file_bytes`. Oversized edits are rejected and the previous context is restored. Oversized application writes raise `ContextFileTooLarge`. If you supply your own `LiveContext`, configure its store's limit directly. Custom stores are responsible for their own bounds and isolation.

`LocalContextStore` requires POSIX directory-descriptor operations, refuses symlink traversal and hard-linked reads, and replaces files atomically. Use `LocalContextStore.in_workdir()` to resolve a trusted workspace path once; direct paths, including checkpoint paths, must not contain symlink components. Sandbox reads use the SDK's bounded-read API where available; a `run_as` user requires the SDK's identity-aware read fallback, whose backend may buffer the file before returning it.

The default local shell scrubs the environment and, on macOS, uses `sandbox-exec` to block network access and writes outside the workspace (with OS temporary/device exceptions). It blocks home-directory reads outside the workspace. On other POSIX platforms it refuses to run unless `allow_unsandboxed=True`; use that option inside an isolated container.

Shell output is retained in a bounded head/tail buffer. Timeouts, cancellation, and completion kill the command's process group, including ordinary background children. Processes that deliberately escape that group require stronger OS/container isolation. These controls do not prevent prompt injection through tool content or edited context.
