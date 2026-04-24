# AI Harness Experiment

Minimal Python harness that orchestrates the Cursor CLI through four stages:

1. **Planner** — produces a kebab-case task slug and writes `.harness/<slug>.plan.md`.
2. **Implementer** — edits files per the plan.
3. **Reviewer** — overwrites `.harness/<slug>.review.md` and exits `0` (pass) or `1` (fail).
4. **Commit + draft PR** — only runs if review passes.

Steps 2+3 loop up to 3 times. If the third review still fails, the final review is appended under a `## Final review (unresolved)` section at the bottom of the plan file and the run aborts without committing.

## Requirements

- `cursor-agent` CLI on `PATH` (authenticated).
- `gh` CLI on `PATH` (authenticated) for the PR step.
- Target directory must be a git repo with an `origin` remote.

## Install the `harness` wrapper

A thin bash wrapper lives at `bin/harness`. It forwards to `harness.py` while
keeping your shell's current directory, so the target repo is whatever folder
you invoke it from.

Put it on `PATH` one of two ways:

```bash
# Option A: symlink into an existing PATH dir
ln -s ~/github/hotelgine/harness-experiment/bin/harness ~/.local/bin/harness

# Option B: add the bin dir to PATH in ~/.zshrc (or equivalent)
echo 'export PATH="$HOME/github/hotelgine/harness-experiment/bin:$PATH"' >> ~/.zshrc
```

Override the Python interpreter with `HARNESS_PYTHON=/path/to/python` if
`python3` isn't what you want.

## Usage

From the root of the target repo:

```bash
harness "add a /health endpoint that returns 200 OK"
```

Or invoke the script directly:

```bash
python /path/to/harness.py "add a /health endpoint that returns 200 OK"
```

Useful flags:

- `--model <slug>` — override the default (`claude-4.6-sonnet-medium-thinking`).
- `--repo <path>` — target a repo other than the current working directory.
- `--skip-pr` — run the plan/implement/review loop but do not commit or open a PR (handy for smoke tests).

## Artifacts

Everything the harness writes lives under `.harness/` (auto-added to `.gitignore`):

- `.harness/<slug>.plan.md` — the plan; gets a `## Final review (unresolved)` section appended if the loop exhausts.
- `.harness/<slug>.review.md` — latest reviewer output, overwritten each iteration.
- `.harness/logs/<slug>-<stage>-<iter>.log` — raw stdout of each `cursor-agent` invocation.

