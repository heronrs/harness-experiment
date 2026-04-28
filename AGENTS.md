# AGENTS.md

Guidance for AI coding agents working in this repository.

## Read first

- **[docs/architecture.md](docs/architecture.md)** — layered architecture
of the `harness` package, module responsibilities, layer contracts,
and conventions for adding new stages or dependencies. Read this
before making any structural change.

## Quick orientation

- The package lives under `src/harness/`. There is no top-level
`harness.py` anymore.
- The CLI is built with [Typer](https://typer.tiangolo.com/) and
exposes three subcommands: `harness run "<task>"` (full pipeline),
`harness continue <token>` (resume), and `harness ask "<text>"`
(one-shot pass-through to cursor-agent, no pipeline / no log files).
- Logging goes through `harness.logging` (Rich-backed). Don't `print()`
from library code.
- Tests live under `tests/` and are run with `pytest`.
- Lint and formatting are enforced by `ruff` (configured in
`pyproject.toml`) and wired in as a pre-commit hook via
`.pre-commit-config.yaml`. Run `pre-commit install` once after cloning
so commits are checked automatically. To check the whole repo manually:
`ruff check . && ruff format --check .`.

## Where to put new code


| Concern                      | Location                                                           |
| ---------------------------- | ------------------------------------------------------------------ |
| New CLI flag or subcommand   | `src/harness/cli.py`                                               |
| New pipeline stage           | `src/harness/services/<stage>.py` + wire into `orchestrator.py`    |
| New external CLI integration | `src/harness/infrastructure/<tool>.py`                             |
| New persisted-state field    | `src/harness/domain/models.py` + bump handling in `state_store.py` |
| New constant or path         | `src/harness/config.py`                                            |
| New prompt template          | `src/harness/prompts.py`                                           |


## Don'ts

- Don't import from upper layers in lower layers (see the layer
contract table in `docs/architecture.md`).
- Don't call `subprocess.run` directly outside `infrastructure/`.
- Don't add dependencies without updating `pyproject.toml` with a
pinned version range.
- Don't write to files outside `.harness/` from inside a stage prompt
unless the plan explicitly requires it.