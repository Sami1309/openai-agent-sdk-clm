"""Identify the implementation behind an evaluation, including uncommitted fixes."""

import hashlib
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def code_fingerprint(root: Path = ROOT) -> str:
    paths = [*root.glob("src/agents_clm/*.py"), *root.glob("benchmarks/*.py"),
             *(root / "benchmarks/contextbench_assets").rglob("*.md"),
             root / "benchmarks/contextbench_assets/paper.yaml", root / "pyproject.toml", root / "uv.lock"]
    digest = hashlib.sha256()
    for path in sorted(paths):
        # Benchmark reports do not change the implementation being evaluated.
        if path.name == "RESULTS.md" or not path.is_file():
            continue
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def provenance() -> dict:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return {
        "code_fingerprint": code_fingerprint(),
        "git_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "environment": {"python": platform.python_version(), **{
            name: version(name) for name in ("openai-agents", "openai", "contextbench", "tiktoken")
        }},
    }
