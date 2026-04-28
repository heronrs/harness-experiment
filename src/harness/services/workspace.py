"""Workspace bootstrapping: ``.harness/`` directory + .gitignore hygiene."""

from __future__ import annotations

from pathlib import Path

from harness.config import LOGS_DIR


def ensure_harness_dir(repo: Path) -> None:
    (repo / LOGS_DIR).mkdir(parents=True, exist_ok=True)
    gitignore = repo / ".gitignore"
    line = ".harness/"
    if gitignore.exists():
        existing = gitignore.read_text()
        if line not in existing.splitlines():
            with gitignore.open("a") as f:
                if not existing.endswith("\n"):
                    f.write("\n")
                f.write(f"{line}\n")
    else:
        gitignore.write_text(f"{line}\n")
