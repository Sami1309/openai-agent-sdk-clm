"""Official ContextBench instances, levels, and method skills (paper Section 3, Appendix D)."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from contextbench import Instance, instruction_for, load_instance
from contextbench.levels import level_knobs

ASSETS = Path(__file__).resolve().parent / "contextbench_assets"
CACHE = Path(__file__).resolve().parent.parent / "runs" / ".instances"
BUDGET = 32_768
RESERVE = 2_048

# Where the paper's task builder placed the skill: (anchor, text before, text after).
_ANCHORS = {
    "kv_store": ("\nThe run ends automatically", "\n", "\n\n"),
    "log_triage": ("\nThe run ends automatically", "\n", "\n\n"),
    "needle_retention": ("\nThe run ends automatically", "\n", "\n\n"),
    "sudoku_sketchpad": ("\n## Turn protocol (IMPORTANT)", "", "\n\n\n"),
}
# Rungs where the figure's baselines used the detailed skill instead of the short one.
_DETAILED = {
    "kv_store": {"R8000", "R16000"},
    "log_triage": {"L6400", "L12800"},
    "needle_retention": {"K2-C192", "K2-C224"},
}


@lru_cache
def paper_config() -> dict[str, Any]:
    return yaml.safe_load((ASSETS / "paper.yaml").read_text(encoding="utf-8"))


def level_entry(family: str, level: str) -> dict[str, Any]:
    spec = paper_config()["families"][family]
    return next(e for e in spec["levels"] if e["name"] == level)


def pressure_of(family: str, level: str) -> float:
    entry = level_entry(family, level)
    return float(entry.get("appendix_pressure") or entry["figure_x"])


def build_instance(family: str, level: str, seed: int) -> Instance:
    directory = CACHE / f"{family}-{level}-seed{seed}"
    if not (directory / "meta.json").exists():
        spec = paper_config()["families"][family]
        module = importlib.import_module(f"contextbench.tasks.{family}.generate")
        module.write_outputs(directory, module.generate(seed=seed, **level_knobs(spec, level_entry(family, level))))
    return load_instance(directory)


def skill_path(method: str, family: str, level: str) -> Path | None:
    """The skill the paper's figure used for this method and rung."""
    skills = ASSETS / "skills"
    if method == "clm":
        return skills / "clm" / f"{family}.md"
    detailed = level in _DETAILED.get(family, ())
    if method == "base" and family == "needle_retention" and not detailed:
        return None  # The figure's base arm saw the scaffold alone at these rungs.
    if family == "sudoku_sketchpad":
        return skills / method / "sudoku_sketchpad.short.md"
    return skills / method / (f"{family}.md" if detailed else f"{family}.short.md")


def task_instruction(instance: Instance, method: str, level: str, workdir: Path) -> str:
    """The scaffold of record with the method's skill placed as the paper's builder did.

    The skills name container paths under /tmp. Each run has its own workspace here.
    """
    text = instruction_for(instance, delivery="bash")
    path = skill_path(method, instance.family, level)
    if path is not None:
        skill = path.read_text(encoding="utf-8")
        anchor, before, after = _ANCHORS[instance.family]
        i = text.rfind(anchor)
        if i < 0:
            raise ValueError(f"No skill anchor in the {instance.family} scaffold")
        text = text[: i + 1] + before + skill.strip("\n") + after + text[i + 1 :]
    return text.replace("/tmp/", f"{workdir}/")
