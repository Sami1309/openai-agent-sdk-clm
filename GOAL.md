# Main goal

**Extend the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) so that an agent can be its own Context Language Model (CLM), rather than relying on the SDK's default context implementation.**

Paper: [Context Language Models](https://arxiv.org/abs/2609.37725) (arXiv:2609.37725).

## What that means

| | Context transition | Who controls the context |
|---|---|---|
| SDK default | `c_{t+1} = c_t ⊕ f(c_t)` (Eq. 1) | The runner appends every item |
| CLM | `c_{t+1} = f(c_t)` (Eq. 2) | The agent, with arbitrary edits |

An agent running as a CLM has its live context mirrored to a file it can edit with general-purpose tools. Its edits become the input to its next model call. If it doesn't edit the file, new output is appended by default.

## Supporting work

- A dashboard that demonstrates how it works and how to run it.
- The benchmarks that evaluate whether it is effective, using the paper's official ContextBench.
- A package structure that follows the Agents SDK's own conventions, so it is easy to use and to change.
