# AI Harness Experiment

Minimal Python harness that orchestrates the Cursor CLI through four stages
(after **creating a work branch** from `origin/main` for each new task — see
Requirements):

1. **Planner** — produces a kebab-case task slug and writes `.harness/<slug>.plan.md`.
2. **Implementer** — edits files per the plan.
3. **Reviewer** — overwrites `.harness/<slug>.review.md` and exits `0` (pass) or `1` (fail).
4. **Commit + draft PR** — only runs if review passes.

Steps 2+3 loop up to 3 times. If the third review still fails, the final review is appended under a `## Final review (unresolved)` section at the bottom of the plan file and the run aborts without committing.

## Requirements

- `cursor-agent` CLI on `PATH` (authenticated).
- `gh` CLI on `PATH` (authenticated) for the PR step.
- Target directory must be a git repo with an `origin` remote.
- For **new** tasks (not `--continue`), the harness runs `git fetch origin main`
then `git checkout -b harness/wip-<timestamp> origin/main`, renames the branch
to `harness/<slug>-<timestamp>` after the planner picks a slug, and does all
implementation on that branch. The default base ref is `main`; adjust the
`BASE_BRANCH` constant in `harness.py` if your default branch differs.
Resuming with `--continue` does not create or switch branches.

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
- `--continue <token>` — resume an interrupted run from its last checkpoint (see below).

## Resuming an interrupted run

Before each stage (planner, every implementer iteration, every reviewer
iteration, and the commit step) the harness writes a checkpoint to
`.harness/<slug>.state.json`. If a run exits non-zero — e.g. a `cursor-agent`
crash, network blip, or `Ctrl-C` — the harness prints a copy-pasteable resume
command to stderr:

```text
[harness] Run interrupted. Resume with:
  harness --continue <token>
```

The token is a base64url-encoded `{repo, slug}` payload, so you can run
`harness --continue <token>` from any directory and it will pick up from the
exact stage and iteration that was about to run (no replanning, no redoing
already-passed iterations). The saved task and model are reused automatically;
pass `--model` to override on resume.

State files are removed on terminal outcomes (successful PR, `--skip-pr`
return, or the loop exhausting `MAX_REVIEW_ITERATIONS`).

## Artifacts

Everything the harness writes lives under `.harness/` (auto-added to `.gitignore`):

- `.harness/<slug>.plan.md` — the plan; gets a `## Final review (unresolved)` section appended if the loop exhausts.
- `.harness/<slug>.review.md` — latest reviewer output, overwritten each iteration.
- `.harness/<slug>.state.json` — checkpoint for `--continue`; deleted on terminal outcomes.
- `.harness/logs/<slug>-<stage>-<iter>.log` — raw stdout of each `cursor-agent` invocation.

