"""Checks the official ContextBench integration without a model."""

import hashlib

import pytest
from agents import ModelBehaviorError, ModelSettings
from agents.run_config import ModelInputData

from agents_clm import ContextSettings
from benchmarks.harnesses import COMPACT_PROMPT, SUMMARY_SYSTEM, CompactionError, OpStream, SummaryManager, run_one
from benchmarks.scripted import ScriptedModel, message, needle_policy
from benchmarks.suite import ASSETS, build_instance, skill_path, task_instruction
from benchmarks.run import validate_carry
from benchmarks.provenance import code_fingerprint

PUBLISHED_CLM_SKILLS = {
    "kv_store": "70695bdca1a7f39d",
    "log_triage": "1a071e820bcc9a93",
    "needle_retention": "e834d24bf004c7ae",
    "sudoku_sketchpad": "378c4e5d928af06f",
}


@pytest.mark.parametrize("field,value", [
    ("source", "scripted"), ("model", "other-model"), ("reasoning", "high"), ("budget", 16_384),
])
def test_carry_rejects_different_experiment_settings(field, value):
    expected = {"source": "live", "model": "gpt-5.4", "reasoning": "default", "budget": 32_768}
    validate_carry(dict(expected), **expected)
    with pytest.raises(ValueError, match=field):
        validate_carry({**expected, field: value}, **expected)


def test_carry_rejects_changed_or_unknown_implementation():
    expected = {"source": "live", "model": "gpt-5.4", "reasoning": "default", "budget": 32_768,
                "code_fingerprint": "new"}
    validate_carry(dict(expected), **expected)
    for old in ("old", None):
        with pytest.raises(ValueError, match="code_fingerprint"):
            validate_carry({**expected, "code_fingerprint": old}, **expected)


def test_fingerprint_detects_uncommitted_code_changes_but_ignores_reports(tmp_path):
    source = tmp_path / "src/agents_clm/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("before")
    before = code_fingerprint(tmp_path)
    (tmp_path / "README.md").write_text("documentation edit")
    assert code_fingerprint(tmp_path) == before
    source.write_text("after")
    assert code_fingerprint(tmp_path) != before


def test_vendored_clm_skills_match_the_paper_byte_for_byte():
    for family, expected in PUBLISHED_CLM_SKILLS.items():
        data = (ASSETS / "skills" / "clm" / f"{family}.md").read_bytes()
        assert hashlib.sha256(data).hexdigest()[:16] == expected


def test_skill_selection_follows_the_figure():
    assert skill_path("base", "needle_retention", "K4-C24") is None
    assert skill_path("base", "needle_retention", "K2-C192").name == "needle_retention.md"
    assert skill_path("summary", "kv_store", "R1000").name == "kv_store.short.md"
    assert skill_path("summary", "kv_store", "R16000").name == "kv_store.md"
    assert skill_path("base", "sudoku_sketchpad", "t100").name == "sudoku_sketchpad.short.md"


def test_skill_is_placed_inside_the_scaffold_and_paths_are_remapped(tmp_path):
    instance = build_instance("needle_retention", "K4-C8", 42)
    text = task_instruction(instance, "clm", "K4-C8", tmp_path)
    assert text.index("delete each filler block") < text.index("The run ends automatically")
    assert f"{tmp_path}/.live_ctx/LIVE_CTX_MAIN.txt" in text and "/tmp/" not in text


def test_stream_follows_the_official_protocol():
    stream = OpStream(build_instance("needle_retention", "K4-C8", 42))
    assert "did NOT advance" in stream.on_command("grep READY_FOR_NEXT_OP notes", 0)
    assert stream.delivered == 1 and not stream.pending
    stream.on_command("false && echo READY_FOR_NEXT_OP", 1)
    assert stream.delivered == 1
    stream.on_command("python3 - <<'PY' && echo READY_FOR_NEXT_OP\nprint(1)\nPY", 0)
    assert stream.delivered == 2 and stream.pending[0].startswith("=== chunk 2/")
    stream.delivered = len(stream.ops)
    stream.on_command("echo READY_FOR_NEXT_OP", 0)
    assert stream.done


async def test_summary_compaction_replaces_everything_but_the_task():
    model = ScriptedModel([[message("the summary")]])
    manager = SummaryManager(ContextSettings(budget=1000, reserve=100), model, ModelSettings())
    task = {"role": "user", "content": "the task"}
    items = [task, {"role": "user", "content": "word " * 900}]
    updated = await manager.update(ModelInputData(input=items, instructions="sys"), items)
    assert model.prompts[0][1][-1]["content"] == COMPACT_PROMPT
    assert updated.input[0] == task and len(updated.input) == 2
    assert "the summary" in updated.input[1]["content"]


async def test_summarizer_does_not_inherit_agent_action_instructions():
    model = ScriptedModel([[message("handoff")]])
    manager = SummaryManager(ContextSettings(budget=1000, reserve=100), model, ModelSettings())
    manager.view = [{"role": "user", "content": "task"}]
    await manager._compact("On every turn call bash with exactly one command.")
    instructions, items = model.prompts[0]
    assert instructions == SUMMARY_SYSTEM
    assert "call bash" in items[0]["content"]
    assert items[0]["role"] == "user"


async def test_empty_summary_is_invalid_and_does_not_destroy_history():
    model = ScriptedModel([[message("")]])
    manager = SummaryManager(ContextSettings(), model, ModelSettings())
    manager.view = [{"role": "user", "content": "task"}, {"role": "user", "content": "keep this fact"}]
    with pytest.raises(CompactionError, match="empty handoff"):
        await manager._compact("sys")
    assert manager.view[-1]["content"] == "keep this fact"
    assert manager.trace.summary()["model_calls"] == 1


async def test_failed_compaction_is_not_retried_as_an_unexecuted_agent_command():
    class Incomplete(ScriptedModel):
        async def get_response(self, *args, **kwargs):
            raise ModelBehaviorError("max_output_tokens")

    manager = SummaryManager(ContextSettings(), Incomplete([]), ModelSettings())
    manager.view = [{"role": "user", "content": "task"}]
    with pytest.raises(CompactionError, match="max_output_tokens"):
        await manager._compact("sys")
    assert manager.view == [{"role": "user", "content": "task"}]
    assert manager.trace.steps[-1]["kind"] == "compaction"


async def test_summary_retains_commentary_before_final_acknowledgement():
    commentary = message("critical fact in the handoff")
    commentary.phase = "commentary"
    final = message("Ready to continue.")
    final.phase = "final_answer"
    model = ScriptedModel([[commentary, final]])
    manager = SummaryManager(ContextSettings(), model, ModelSettings())
    manager.view = [{"role": "user", "content": "task"}]
    await manager._compact("sys")
    assert "critical fact in the handoff" in manager.view[-1]["content"]
    assert "Ready to continue." in manager.view[-1]["content"]


async def test_compaction_shows_tool_calls_as_tool_calls():
    """Regression: plain-text history made a real model write a tool call as its summary."""
    model = ScriptedModel([[message("the summary")]])
    manager = SummaryManager(ContextSettings(budget=1000, reserve=100), model, ModelSettings())
    call_item = {"type": "function_call", "call_id": "c1", "name": "bash", "arguments": "{}"}
    output_item = {"type": "function_call_output", "call_id": "c1", "output": "word " * 900}
    items = [{"role": "user", "content": "the task"}, call_item, output_item]
    await manager.update(ModelInputData(input=items, instructions="sys"), items)
    assert all(not str(i.get("content", "")).startswith("bash ") for i in model.prompts[0][1])


async def test_scripted_clm_survives_pressure_where_base_hits_the_wall():
    base = (await run_one("needle_retention", "K4-C24", 42, "base", ScriptedModel(needle_policy("base"))))["record"]
    clm = (await run_one("needle_retention", "K4-C24", 42, "clm", ScriptedModel(needle_policy("clm"))))["record"]
    assert base["terminated"] == "budget_wall" and base["score"] < 1
    assert base["grade"]["graded_from"] == "snapshots"
    assert clm["terminated"] == "stream_exhausted", clm
    assert clm["score"] == 1 and clm["edits_applied"] > 0
