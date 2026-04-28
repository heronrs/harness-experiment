"""Typer-based command-line entry point.

Two subcommands:

- ``harness run "<task>"`` — start a new task on a fresh feature branch.
- ``harness continue <token>`` — resume an interrupted run from a saved checkpoint.

Backwards-compatible shortcut: ``harness "<task>"`` is treated as ``harness run "<task>"``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from harness.config import DEFAULT_MODEL
from harness import orchestrator

app = typer.Typer(
    help="Minimal AI coding harness built on top of the Cursor CLI.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command(help="Run a new task: branch -> plan -> implement/review loop -> draft PR.")
def run(
    task: str = typer.Argument(..., help="Natural-language description of the task."),
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", "-m", help="cursor-agent model slug."
    ),
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to the target git repository (default: cwd).",
    ),
    skip_pr: bool = typer.Option(
        False, "--skip-pr", help="Skip commit/push/PR after a passing review."
    ),
) -> None:
    if not (repo / ".git").exists():
        typer.secho(f"[harness] ERROR: {repo} is not a git repository.", fg="red", err=True)
        raise typer.Exit(code=1)
    orchestrator.run_new_task(task=task, model=model, repo=repo, skip_pr=skip_pr)


@app.command(name="continue", help="Resume an interrupted run from a checkpoint token.")
def continue_run(
    token: str = typer.Argument(..., help="Resume token printed by a previous run."),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override the model saved in the checkpoint."
    ),
    skip_pr: bool = typer.Option(
        False, "--skip-pr", help="Skip commit/push/PR after a passing review."
    ),
) -> None:
    orchestrator.resume_from_token(
        token=token, model_override=model, skip_pr=skip_pr
    )


if __name__ == "__main__":
    app()
