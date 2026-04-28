"""Git operations used by the harness.

All functions are pure wrappers around the ``git`` CLI; no in-process
git library is used so the behavior matches what a developer sees on
their own terminal.
"""

from __future__ import annotations

import subprocess
import time

from harness.config import BASE_BRANCH
from harness.domain.models import HarnessContext
from harness.infrastructure.shell import sh
from harness.logging import die, log


def checkout_feature_branch_from_origin_main(ctx: HarnessContext) -> None:
    """Create and switch to a new branch from ``origin/<BASE_BRANCH>``."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    ctx.branch_ts = ts
    wip = f"harness/wip-{ts}"
    sh(["git", "fetch", "origin", BASE_BRANCH], cwd=ctx.repo)
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/remotes/origin/{BASE_BRANCH}"],
        cwd=ctx.repo,
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        die(
            f"ref origin/{BASE_BRANCH} not found after "
            f"`git fetch origin {BASE_BRANCH}`. "
            "Ensure remote `origin` exists and the default branch is available as "
            f"`origin/{BASE_BRANCH}`."
        )
    sh(["git", "checkout", "-b", wip, f"origin/{BASE_BRANCH}"], cwd=ctx.repo)
    log(f"checked out new branch {wip!r} from origin/{BASE_BRANCH}")


def rename_feature_branch_to_slug(ctx: HarnessContext) -> None:
    """Rename ``harness/wip-<ts>`` to ``harness/<slug>-<ts>``."""
    assert ctx.slug and ctx.branch_ts
    final = f"harness/{ctx.slug}-{ctx.branch_ts}"
    sh(["git", "branch", "-m", final], cwd=ctx.repo)
    log(f"renamed branch to {final!r}")


def working_tree_dirty(ctx: HarnessContext) -> bool:
    status = sh(
        ["git", "status", "--porcelain"], cwd=ctx.repo, capture=True
    ).stdout.strip()
    return bool(status)


def commit_all_and_push(ctx: HarnessContext, message: str) -> None:
    sh(["git", "add", "-A"], cwd=ctx.repo)
    sh(["git", "commit", "-m", message], cwd=ctx.repo)
    sh(["git", "push", "-u", "origin", "HEAD"], cwd=ctx.repo)
