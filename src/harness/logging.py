"""Rich-powered logging helpers used across the harness.

Centralizing this here keeps presentation concerns out of every layer
and makes it easy to swap formatting later.
"""

from __future__ import annotations

import sys

from rich.console import Console

_stdout = Console()
_stderr = Console(stderr=True)


def log(msg: str) -> None:
    """User-facing progress log line."""
    _stdout.print(f"[bold cyan]\\[harness][/] {msg}")


def warn(msg: str) -> None:
    _stderr.print(f"[bold yellow]\\[harness][/] {msg}")


def die(msg: str, code: int = 1) -> None:
    """Print an error and exit. Used as a hard-stop across the codebase."""
    _stderr.print(f"[bold red]\\[harness] ERROR:[/] {msg}")
    sys.exit(code)


def console() -> Console:
    """Expose the stdout console for callers that need to stream raw text
    (e.g. tee-ing cursor-agent output)."""
    return _stdout
