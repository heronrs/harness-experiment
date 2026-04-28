# Architecture

This document describes how the `harness` package is organized so future
agents (and humans) can extend it without breaking the existing patterns.

## Goals

- **Single responsibility per module.** Each file does one thing.
- **Layered dependencies.** Dependencies only point downward; lower
layers never import upper ones.
- **No I/O in the domain layer.** Domain types are pure data so they can
be exercised in unit tests without a filesystem, network, or
subprocess.

## Layers

```
                ┌────────────────────────┐
                │         cli.py         │   Typer commands (presentation)
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │    orchestrator.py     │   use case: full pipeline + resume
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │       services/        │   per-stage application logic
                │  planner / implementer │
                │  reviewer / pr / slug  │
                │  workspace             │
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │    infrastructure/     │   external systems
                │  shell / cursor_agent  │
                │  git / github          │
                │  state_store          │
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │        domain/         │   pure data
                │       models.py        │
                └────────────────────────┘
```

Cross-cutting modules used by every layer above `domain`:

- `harness/config.py` — constants (model defaults, paths, timeouts).
- `harness/prompts.py` — prompt templates passed to `cursor-agent`.
- `harness/logging.py` — Rich-powered `log` / `warn` / `die` helpers.

### Layer contracts


| Layer            | May import from                                             | Must NOT import from              |
| ---------------- | ----------------------------------------------------------- | --------------------------------- |
| `domain`         | stdlib only                                                 | anything else in `harness`        |
| `infrastructure` | `domain`, `config`, `logging`, stdlib, external CLIs        | `services`, `orchestrator`, `cli` |
| `services`       | `domain`, `infrastructure`, `config`, `prompts`, `logging`  | `orchestrator`, `cli`             |
| `orchestrator`   | `services`, `infrastructure`, `domain`, `config`, `logging` | `cli`                             |
| `cli`            | `orchestrator`, `config`, `logging`                         | —                                 |


If you find yourself wanting to reach across these layers, that's a
signal the responsibility belongs in a different module.

## Module index

### `domain/models.py`

Dataclasses only. `HarnessContext` carries per-run state in memory;
`RunState` is the serialized checkpoint payload.

### `infrastructure/`

- `**shell.py**` — single `sh()` wrapper around `subprocess.run` with
consistent logging. All shell-out paths should funnel through here.
- `**cursor_agent.py**` — `ensure_cursor_agent()` and `run_agent()`. The
only place that spawns `cursor-agent`. Streams output to the terminal
AND tees to `.harness/logs/<slug>-<stage>-<iter>.log`.
- `**git.py**` — branch creation, rename, dirty-tree check, commit+push.
- `**github.py**` — `gh` CLI wrappers (currently just `open_draft_pr`).
- `**state_store.py**` — JSON-on-disk checkpoints + base64url resume tokens.

### `services/`

Each stage is one module with one entry point. Stages mutate the
`HarnessContext` in-place (e.g. setting `slug`, `plan_path`).

- `**slug.py**` — `sanitize_slug()` + the `SLUG_RE` regex.
- `**workspace.py**` — `ensure_harness_dir()` + `.gitignore` hygiene.
- `**planner.py**` — runs the planner agent, validates the slug,
promotes the temp plan file to its final path.
- `**implementer.py**` — runs the implementer agent for one iteration.
- `**reviewer.py**` — runs the reviewer agent and parses pass/fail;
appends the final review to the plan when the loop is exhausted.
- `**pr.py**` — composes commit message + PR body and delegates to
`infrastructure.git` and `infrastructure.github`.

### `orchestrator.py`

Owns the state machine: `planner → (implementer → reviewer) × N → pr`.
Two entry points: `run_new_task()` for fresh runs, `resume_from_token()`
for `harness continue`. The `_run_loop()` helper is shared between them
and handles `SystemExit` to print the resume hint on failure.

### `cli.py`

Typer app exposing two subcommands: `run` and `continue`. The CLI never
contains business logic — it parses arguments, validates the repo path,
and delegates to the orchestrator.

## Conventions

### Logging

Use `harness.logging.log()` for progress, `warn()` for non-fatal
issues, and `die()` for fatal errors. They render through Rich, so the
terminal output is colorized and consistent. Do not `print()` directly
from library code (CLI exit messages are the one exception).

### Error handling

Lower layers raise `SystemExit` via `die()` rather than custom
exceptions. The orchestrator catches `SystemExit` exactly once to print
the resume hint, then re-raises. Don't swallow it elsewhere.

### Paths

Repo-relative paths are stored as `pathlib.Path` instances rooted at
`HARNESS_DIR` (`.harness/`). The `repo` field on `HarnessContext` is the
absolute path; combine the two only at the I/O boundary.

### Adding a new stage

1. Add a prompt template in `prompts.py`.
2. Create `services/<stage>.py` with a single `run_<stage>(ctx, ...)`
  function that calls `infrastructure.cursor_agent.run_agent()`.
3. Wire it into `orchestrator._run_loop()` and add a corresponding
  `next_stage` value.
4. Update the state-machine description in this doc.

### Adding a new external dependency (CLI tool)

Wrap it in a new module under `infrastructure/`. Never call
`subprocess.run` directly from `services/` or higher.

### Tests

Live under `tests/`. Pure modules (`slug`, `state_store`, `domain`)
have direct unit tests. Stage modules and the orchestrator are best
exercised with monkeypatched `run_agent` / git / gh. Use `pytest`
fixtures (`tmp_path`) for filesystem state.

## Run artifacts

Every run writes under `<repo>/.harness/`:

- `<slug>.plan.md` — planner output; gets a `## Final review (unresolved)`
section appended when the loop exhausts.
- `<slug>.review.md` — latest reviewer output.
- `<slug>.state.json` — checkpoint for `harness continue`.
- `logs/<slug>-<stage>-<iter>.log` — raw `cursor-agent` stdout.

These are git-ignored automatically by `services.workspace`.