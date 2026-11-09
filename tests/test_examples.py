"""Runs every example end to end, with a scripted model in place of the API."""

import importlib.util
from pathlib import Path

import pytest
from agents.models.multi_provider import MultiProvider

from benchmarks.scripted import ScriptedModel, message

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize("name", sorted(p.stem for p in EXAMPLES.glob("*.py")))
async def test_example_runs(name, monkeypatch, capsys):
    model = ScriptedModel(lambda *_: [message("done")])
    monkeypatch.setattr(MultiProvider, "get_model", lambda self, model_name: model)
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    await module.main()
    assert "done" in capsys.readouterr().out
