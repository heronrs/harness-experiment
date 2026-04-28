"""Cursor CLI invocation: discovery + streaming subprocess execution.

Owns the only call site for the ``cursor-agent`` binary. Streams output
to both the user's terminal (via the rich console) and a per-stage log
file under ``.harness/logs/``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

from harness.config import AGENT_TIMEOUT_SECONDS, LOGS_DIR
from harness.domain.models import HarnessContext
from harness.logging import die, log


def ensure_cursor_agent() -> str:
    binary = shutil.which("cursor-agent")
    if not binary:
        die("`cursor-agent` not found on PATH. Install the Cursor CLI first.")
    assert binary is not None
    return binary


def run_agent(
    prompt: str,
    *,
    ctx: HarnessContext,
    stage: str,
    iteration: int,
    plan_mode: bool = False,
) -> tuple[int, str]:
    """Invoke ``cursor-agent -p`` non-interactively and tee output to a log file."""
    binary = ensure_cursor_agent()
    slug_part = ctx.slug or "bootstrap"
    log_path = ctx.repo / LOGS_DIR / f"{slug_part}-{stage}-{iteration}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        binary,
        "--print",
        "--force",
        "--output-format",
        "text",
        "--model",
        ctx.model,
    ]
    if plan_mode:
        cmd += ["--mode", "plan"]
    cmd.append(prompt)

    log(f"stage={stage} iter={iteration} model={ctx.model} plan_mode={plan_mode}")
    log(f"log -> {log_path}")

    with log_path.open("w") as logfile:
        logfile.write(f"$ {' '.join(cmd[:-1])} <prompt>\n")
        logfile.write(f"--- PROMPT ---\n{prompt}\n--- OUTPUT ---\n")
        logfile.flush()

        proc = subprocess.Popen(
            cmd,
            cwd=ctx.repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        stdout_chunks: list[str] = []
        start = time.time()
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                stdout_chunks.append(line)
                logfile.write(line)
                logfile.flush()
                sys.stdout.write(line)
                sys.stdout.flush()
                if time.time() - start > AGENT_TIMEOUT_SECONDS:
                    proc.kill()
                    die(
                        f"agent stage '{stage}' timed out after "
                        f"{AGENT_TIMEOUT_SECONDS}s"
                    )
        finally:
            proc.wait()

    stdout = "".join(stdout_chunks)
    return proc.returncode, stdout
