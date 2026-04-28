"""Cursor CLI invocation: discovery + streaming subprocess execution.

Owns the only call site for the ``cursor-agent`` binary. Invokes the
agent in ``--output-format stream-json`` mode, parses each event as it
arrives, and dispatches it to:

- the user's terminal (rendered for humans by ``agent_stream``),
- optionally, a raw JSONL log under ``.harness/logs/`` (preserved
  verbatim so future sinks — Datadog, dashboards, etc. — can replay it).

Two entry points share the streaming core:

- ``run_agent`` — used by pipeline stages; writes a per-stage JSONL log.
- ``run_agent_ephemeral`` — used by ad-hoc commands like ``harness ask``;
  no log file, no checkpoint context required.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import IO

from harness.config import AGENT_TIMEOUT_SECONDS, LOGS_DIR
from harness.domain.models import HarnessContext
from harness.infrastructure.agent_stream import (
    classify_delta,
    delta_stream_prefix,
    delta_stream_suffix,
    parse_event_line,
    render_event,
)
from harness.logging import die, log


def ensure_cursor_agent() -> str:
    binary = shutil.which("cursor-agent")
    if not binary:
        die("`cursor-agent` not found on PATH. Install the Cursor CLI first.")
    assert binary is not None
    return binary


def _build_cmd(binary: str, *, prompt: str, model: str, plan_mode: bool) -> list[str]:
    cmd = [
        binary,
        "--print",
        "--force",
        "--output-format",
        "stream-json",
        "--stream-partial-output",
        "--model",
        model,
    ]
    if plan_mode:
        cmd += ["--mode", "plan"]
    cmd.append(prompt)
    return cmd


def _stream_agent(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_label: str,
    logfile: IO[str] | None,
) -> tuple[int, str]:
    """Run ``cursor-agent`` and stream rendered events to stdout.

    ``logfile``, when provided, receives the raw JSONL stream verbatim.
    ``timeout_label`` is included in the timeout error message so the
    user can tell which invocation hung.
    """
    assistant_text: list[str] = []
    # Track which kind of token-delta stream is currently being printed
    # ("assistant" or "thinking"). Consecutive deltas of the same kind
    # stay on one line; switching kinds (or any non-delta event) flushes
    # a newline first so the next chunk starts cleanly.
    active_delta_kind: str | None = None

    def _flush_delta_newline() -> None:
        nonlocal active_delta_kind
        if active_delta_kind is not None:
            sys.stdout.write(delta_stream_suffix(active_delta_kind) + "\n")
            active_delta_kind = None

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
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
            if logfile is not None:
                logfile.write(raw_line)
                logfile.flush()

            event = parse_event_line(raw_line)
            if event is None:
                _flush_delta_newline()
                sys.stdout.write(raw_line)
                sys.stdout.flush()
            else:
                delta = classify_delta(event)
                if delta is not None:
                    kind, text = delta
                    if active_delta_kind != kind:
                        _flush_delta_newline()
                        sys.stdout.write(delta_stream_prefix(kind))
                        active_delta_kind = kind
                    if kind == "assistant":
                        assistant_text.append(text)
                    sys.stdout.write(text)
                    sys.stdout.flush()
                else:
                    rendered = render_event(event)
                    if rendered is not None:
                        _flush_delta_newline()
                        sys.stdout.write(rendered + "\n")
                        sys.stdout.flush()

            if time.time() - start > AGENT_TIMEOUT_SECONDS:
                proc.kill()
                _flush_delta_newline()
                die(
                    f"agent {timeout_label} timed out after "
                    f"{AGENT_TIMEOUT_SECONDS}s"
                )
    finally:
        _flush_delta_newline()
        proc.wait()

    return proc.returncode, "".join(assistant_text)


def run_agent(
    prompt: str,
    *,
    ctx: HarnessContext,
    stage: str,
    iteration: int,
    plan_mode: bool = False,
) -> tuple[int, str]:
    """Invoke ``cursor-agent`` for a pipeline stage.

    Streams events to the terminal and tees the raw JSONL stream to
    ``.harness/logs/<slug>-<stage>-<iter>.jsonl``. Returns
    ``(exit_code, accumulated_assistant_text)``.
    """
    binary = ensure_cursor_agent()
    slug_part = ctx.slug or "bootstrap"
    log_path = ctx.repo / LOGS_DIR / f"{slug_part}-{stage}-{iteration}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = _build_cmd(binary, prompt=prompt, model=ctx.model, plan_mode=plan_mode)

    log(f"stage={stage} iter={iteration} model={ctx.model} plan_mode={plan_mode}")
    log(f"log -> {log_path}")

    with log_path.open("w") as logfile:
        logfile.write(f"# cmd: {' '.join(cmd[:-1])} <prompt>\n")
        logfile.write(f"# prompt: {prompt!r}\n")
        logfile.flush()
        return _stream_agent(
            cmd,
            cwd=ctx.repo,
            timeout_label=f"stage '{stage}'",
            logfile=logfile,
        )


def run_agent_ephemeral(
    prompt: str,
    *,
    cwd: Path,
    model: str,
    plan_mode: bool = False,
) -> tuple[int, str]:
    """Invoke ``cursor-agent`` for a one-shot ad-hoc query.

    No checkpoint context, no log file written. Streams events to the
    terminal exactly like :func:`run_agent`. Used by ``harness ask``.
    """
    binary = ensure_cursor_agent()
    cmd = _build_cmd(binary, prompt=prompt, model=model, plan_mode=plan_mode)
    return _stream_agent(cmd, cwd=cwd, timeout_label="ask", logfile=None)
