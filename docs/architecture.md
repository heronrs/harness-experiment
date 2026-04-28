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
                │  reviewer / code_qa    │
                │  review_phase          │
                │  code_qa_phase         │
                │  pr / slug             │
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
- `**cursor_agent.py**` — `ensure_cursor_agent()`, `run_agent()` (for
pipeline stages, tees the JSONL stream to
`.harness/logs/<slug>-<stage>-<iter>.jsonl`), and `run_agent_ephemeral()`
(for one-shot ad-hoc queries, no log file). Both share a private
`_stream_agent()` helper that owns the subprocess + event-rendering
loop. The only place that spawns `cursor-agent`.
- `**agent_stream.py**` — pure functions that parse and render a single
`stream-json` event for the terminal. No I/O, no subprocess.
- `**git.py**` — branch creation, rename, dirty-tree check, commit+push.
- `**github.py**` — `gh` CLI wrappers (currently just `open_draft_pr`).
- `**state_store.py**` — JSON-on-disk checkpoints + base64url resume tokens.

### `services/`

Each stage is one module with one entry point. Stages mutate the
`HarnessContext` in-place (e.g. setting `slug`, `plan_path`).

Modules come in two flavors:

- **Stage modules** run a single agent invocation: `planner`,
 `implementer`, `reviewer`, `code_qa`.
- **Phase modules** own an iteration loop over one or more stages and
 are responsible for that loop's checkpointing and exhaustion handling:
 `review_phase`, `code_qa_phase`. The orchestrator only talks to phase
 modules (and to `planner` / `pr`, which are single-shot).

This split keeps the orchestrator a flat sequence and makes adding a
new phase a localized change (Open/Closed): add `services/<thing>_phase.py`
and one `if next_stage in <THING>_STAGES` block in `_run_loop()`.

- `**slug.py**` — `sanitize_slug()` + the `SLUG_RE` regex.
- `**workspace.py**` — `ensure_harness_dir()` + `.gitignore` hygiene.
- `**planner.py**` — runs the planner agent, validates the slug,
promotes the temp plan file to its final path, and populates
`plan_path` / `review_path` / `code_qa_path` on the context.
- `**implementer.py**` — runs the implementer agent for one iteration.
Stage-agnostic: callers pass a `guidance` string so the implementer
never branches on whether it's recovering from a review or qa failure.
- `**reviewer.py**` — runs the reviewer agent and parses pass/fail;
exposes `append_final_review_to_plan()` for the review phase to call
on exhaustion.
- `**code_qa.py**` — runs the code-qa agent against the target repo's
existing lint/typecheck/format suite (tests are out of scope).
Mirrors `reviewer.py`'s shape, including
`append_final_code_qa_to_plan()`.
- `**review_phase.py**` — owns the implementer↔reviewer loop, capped
at `MAX_REVIEW_ITERATIONS`. On success, leaves checkpoint at
`code_qa`. On exhaustion, appends the final review and `die()`s.
- `**code_qa_phase.py**` — owns the code-qa↔implementer loop, capped at
`MAX_CODE_QA_ITERATIONS`. On success, leaves checkpoint at `commit`. On
exhaustion, appends the final qa report and `die()`s.
- `**pr.py**` — composes commit message + PR body and delegates to
`infrastructure.git` and `infrastructure.github`.
- `**ask.py**` — one-shot ad-hoc query that bypasses the pipeline.
Forwards a prompt to ``cursor-agent`` via the ephemeral runner (no
log file, no checkpoint context) and returns the exit code. Used by
the ``harness ask`` subcommand.

### `orchestrator.py`

Owns the state machine:
`planner → review-phase → code-qa-phase → pr`,
where each phase internally loops:

- review-phase: `(implementer → reviewer) × MAX_REVIEW_ITERATIONS`
- code-qa-phase: `(code_qa → implementer_code_qa_fix) × MAX_CODE_QA_ITERATIONS`

Three entry points:

- `run_new_task()` for fresh runs of the pipeline.
- `resume_from_token()` for `harness continue` (resumes from
 a checkpoint).
- `ask()` for one-shot pass-throughs that don't touch the pipeline at
 all. Re-exposes `services.ask.run_ask()` so the CLI's "talks only to
 orchestrator" layer rule still holds.

The `_run_loop()` helper is shared between the two pipeline entry points
and handles `SystemExit` to print the resume hint on failure. It
dispatches to a phase module by checking which phase's `*_STAGES` set
contains the current `next_stage` value, so resume-mid-phase works
without per-stage branching here.

### `cli.py`

Typer app exposing three subcommands: `run`, `continue`, and `ask`. The
CLI never contains business logic — it parses arguments, validates the
repo path, and delegates to the orchestrator.

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
or `## Final code-qa (unresolved)` section appended when the
corresponding phase loop exhausts.
- `<slug>.review.md` — latest reviewer output.
- `<slug>.code_qa.md` — latest code-qa output.
- `<slug>.state.json` — checkpoint for `harness continue`.
- `logs/<slug>-<stage>-<iter>.log` — raw `cursor-agent` stdout.

These are git-ignored automatically by `services.workspace`.