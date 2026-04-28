"""GitHub interactions via the ``gh`` CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

from harness.infrastructure.shell import sh
from harness.logging import die, log


def ensure_gh() -> None:
    if not shutil.which("gh"):
        die("`gh` CLI not found; cannot open a PR.")


def open_draft_pr(*, repo: Path, title: str, body: str) -> None:
    ensure_gh()
    sh(
        ["gh", "pr", "create", "--draft", "--title", title, "--body", body],
        cwd=repo,
    )
    log("draft PR opened.")
