"""Ask stage: one-shot ad-hoc query, no pipeline, no logs.

Bypasses the full plan/implement/review/qa pipeline and just forwards
a prompt to ``cursor-agent``, streaming the result to the terminal.

Used by the ``harness ask`` CLI subcommand. There's no ``HarnessContext``
because there's no checkpoint state, no slug, no plan file — this is
deliberately a stateless wrapper.
"""

from __future__ import annotations

from pathlib import Path

from harness.infrastructure.cursor_agent import run_agent_ephemeral


def run_ask(*, prompt: str, model: str, cwd: Path) -> int:
    """Forward ``prompt`` to ``cursor-agent`` and stream the result.

    Returns the agent's exit code.
    """
    code, _ = run_agent_ephemeral(prompt, cwd=cwd, model=model)
    return code
