"""Typer-based command-line entry point.

Subcommands:

- ``harness run "<task>"`` — start a new task on a fresh feature branch.
- ``harness continue <token>`` — resume an interrupted run from a saved
  checkpoint.
- ``harness ask "<text>"`` — one-shot pass-through to ``cursor-agent``,
  no pipeline, no log files.

Backwards-compatible shortcut: ``harness -t <url>`` is treated as
``harness run -t <url>``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from harness import orchestrator
from harness.config import DEFAULT_MODEL

app = typer.Typer(
    help="Minimal AI coding harness built on top of the Cursor CLI.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    ticket: str | None = typer.Option(
        None,
        "--ticket",
        "-t",
        help="Jira task URL (shortcut for 'harness run -t <url>').",
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m"),
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    skip_pr: bool = typer.Option(False, "--skip-pr"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if ticket is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()
    if not (repo / ".git").exists():
        typer.secho(
            f"[harness] ERROR: {repo} is not a git repository.",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=1)
    orchestrator.run_from_ticket(
        ticket_url=ticket, model=model, repo=repo, skip_pr=skip_pr
    )


@app.command(
    help="Run a new task: branch -> plan -> implement/review loop -> draft PR."
)
def run(
    task: str | None = typer.Argument(
        None, help="Natural-language description of the task."
    ),
    ticket: str | None = typer.Option(
        None,
        "--ticket",
        "-t",
        help=(
            "Jira task URL. Fetches task via Atlassian MCP instead of a text argument."
        ),
    ),
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
        typer.secho(
            f"[harness] ERROR: {repo} is not a git repository.",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=1)

    if ticket:
        orchestrator.run_from_ticket(
            ticket_url=ticket, model=model, repo=repo, skip_pr=skip_pr
        )
    elif task:
        orchestrator.run_new_task(task=task, model=model, repo=repo, skip_pr=skip_pr)
    else:
        typer.secho(
            "[harness] ERROR: Provide either a TASK argument or --ticket/-t.",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=1)


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
    orchestrator.resume_from_token(token=token, model_override=model, skip_pr=skip_pr)


@app.command(
    help=(
        "One-shot pass-through to cursor-agent: streams the response and "
        "exits. No plan, no review, no log files."
    )
)
def ask(
    text: str = typer.Argument(..., help="Prompt text to send to cursor-agent."),
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
        help="Working directory for the agent (default: cwd).",
    ),
) -> None:
    code = orchestrator.ask(prompt=text, model=model, repo=repo)
    if code != 0:
        raise typer.Exit(code=code)


if __name__ == "__main__":
    app()
