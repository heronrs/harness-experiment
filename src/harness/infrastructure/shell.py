"""Thin wrapper around ``subprocess.run`` with consistent logging."""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness.logging import log


def sh(
    cmd: list[str],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
    )
