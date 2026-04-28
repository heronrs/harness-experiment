"""Cursor CLI invocation: discovery + streaming subprocess execution.

Owns the only call site for the ``cursor-agent`` binary. Invokes the
agent in ``--output-format stream-json`` mode, parses each event as it
arrives, and dispatches it to:

- the user's terminal (rendered for humans by ``agent_stream``),
- a per-stage raw JSONL log under ``.harness/logs/`` (preserved
  verbatim so future sinks — Datadog, dashboards, etc. — can replay it).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

from harness.config import AGENT_TIMEOUT_SECONDS, LOGS_DIR
from harness.domain.models import HarnessContext
from harness.infrastructure.agent_stream import parse_event_line, render_event
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
    """Invoke ``cursor-agent`` non-interactively and stream events.

    Returns ``(exit_code, accumulated_assistant_text)``. The accumulated
    text is reconstructed from the assistant text deltas so callers that
    want the final answer don't have to reparse the JSONL log.
    """
    binary = ensure_cursor_agent()
    slug_part = ctx.slug or "bootstrap"
    log_path = ctx.repo / LOGS_DIR / f"{slug_part}-{stage}-{iteration}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        binary,
        "--print",
        "--force",
        "--output-format",
        "stream-json",
        "--stream-partial-output",
        "--model",
        ctx.model,
    ]
    if plan_mode:
        cmd += ["--mode", "plan"]
    cmd.append(prompt)

    log(f"stage={stage} iter={iteration} model={ctx.model} plan_mode={plan_mode}")
    log(f"log -> {log_path}")

    assistant_text: list[str] = []
    in_delta_stream = False

    def _flush_delta_newline() -> None:
        """Insert a newline if we're switching away from a delta stream."""
        nonlocal in_delta_stream
        if in_delta_stream:
            sys.stdout.write("\n")
            in_delta_stream = False

    with log_path.open("w") as logfile:
        logfile.write(f"# cmd: {' '.join(cmd[:-1])} <prompt>\n")
        logfile.write(f"# prompt: {prompt!r}\n")
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

        start = time.time()
        assert proc.stdout is not None
        try:
            for raw_line in proc.stdout:
                logfile.write(raw_line)
                logfile.flush()

                event = parse_event_line(raw_line)
                if event is None:
                    _flush_delta_newline()
                    sys.stdout.write(raw_line)
                    sys.stdout.flush()
                else:
                    rendered = render_event(event)
                    if rendered is not None:
                        is_delta = (
                            event.get("type") == "assistant" and "timestamp_ms" in event
                        )
                        if is_delta:
                            assistant_text.append(rendered)
                            sys.stdout.write(rendered)
                            in_delta_stream = True
                        else:
                            _flush_delta_newline()
                            sys.stdout.write(rendered + "\n")
                        sys.stdout.flush()

                if time.time() - start > AGENT_TIMEOUT_SECONDS:
                    proc.kill()
                    _flush_delta_newline()
                    die(
                        f"agent stage '{stage}' timed out after "
                        f"{AGENT_TIMEOUT_SECONDS}s"
                    )
        finally:
            _flush_delta_newline()
            proc.wait()

    return proc.returncode, "".join(assistant_text)
