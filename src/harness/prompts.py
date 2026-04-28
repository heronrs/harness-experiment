"""Prompt templates for each cursor-agent stage.

Templates use ``str.format`` with named placeholders. All paths are
formatted as strings relative to the target repo root.
"""

from __future__ import annotations

PLANNER_PROMPT = """\
You are the PLANNER stage of an automated coding harness.

Task from the user:
<<<
{task}
>>>

Do the following, in this exact order:

1. Come up with a short kebab-case slug that describes the task
   (lowercase, hyphen-separated, at most 6 words, ASCII only,
   e.g. `add-health-endpoint`).
2. Write that slug and NOTHING ELSE (no quotes, no surrounding whitespace,
   no markdown formatting, no trailing newline beyond one) as the entire
   contents of the file `{slug_path}`. The `.md` extension is only there
   because plan mode is restricted to markdown files; the file's contents
   must still be just the bare slug, e.g. a one-line file containing
   `add-health-endpoint`. This file MUST exist when you finish, or the
   harness will abort.
3. Then read the repository structure as needed and write a concrete,
   step-by-step implementation plan to `{plan_path}`. The plan should
   cover: files to touch, new functions/classes, data flow,
   edge cases, and a short test strategy.

Constraints:
- You are in plan mode: you may only write to `{slug_path}` and `{plan_path}`.
  Do NOT edit any other files.
- Keep the plan focused and actionable. No fluff.
"""


IMPLEMENTER_PROMPT = """\
You are the IMPLEMENTER stage of an automated coding harness.
Iteration: {iteration} of {max_iterations}.

Read `{plan_path}` in full and implement the task it describes.

{review_guidance}

Rules:
- Make all code changes required by the plan.
- Run any quick local checks you have available (formatters, linters, type
  checkers) and fix issues they surface. A dedicated code-qa stage will
  run the project's lint/typecheck/format suite afterwards.
- DO NOT commit, push, or create branches. Leave changes in the working tree.
- DO NOT modify files under `.harness/` — they are harness bookkeeping.
"""


IMPLEMENTER_FIRST_ITERATION_GUIDANCE = (
    "This is the first implementation attempt, so there is no prior feedback yet."
)


IMPLEMENTER_REVIEW_FOLLOWUP_GUIDANCE = """\
A previous review found issues. Read `{review_path}` in full and address
EVERY problem it raises before finishing. If the review asks you to change
behavior, change behavior; if it asks for tests, add tests.
"""


IMPLEMENTER_CODE_QA_FOLLOWUP_GUIDANCE = """\
A previous code-qa run found lint/typecheck/format failures. Read
`{code_qa_path}` in full and fix EVERY failure it lists. Do not change
behavior beyond what's needed to make those checks pass.
"""


REVIEWER_PROMPT = """\
You are the REVIEWER stage of an automated coding harness.

Your job:
1. Inspect the current working tree changes (use `git status` and
   `git diff` — compare against `origin/main` if it exists, otherwise
   against `HEAD`).
2. Evaluate the diff against `{plan_path}` for:
   - correctness and obvious bugs
   - missing test coverage for new behavior
   - security concerns
   - adherence to the plan
3. Overwrite `{review_path}` with your findings in markdown. Be specific:
   cite file paths and line numbers. If there are no issues, say so briefly.
4. The VERY LAST line of `{review_path}` MUST be exactly one of:
     STATUS: PASS
     STATUS: FAIL
5. After writing the file, exit the agent with:
     - exit code 0 if the change is merge-ready (STATUS: PASS)
     - exit code 1 if it is not (STATUS: FAIL)
   You can do this by running `exit 0` or `exit 1` in a shell tool call
   as your final action.

Rules:
- Do NOT edit any source files. The only file you may write is `{review_path}`.
- Be strict but fair. A tiny nit is not a FAIL; a real bug or missing test is.
"""


JIRA_FETCH_PROMPT = """\
Use the Atlassian MCP tool to fetch the Jira issue at this URL: {url}

Output ONLY the following block and nothing else:
<TASK_DESCRIPTION>
<one-line summary of the issue>

<full description of the issue>
</TASK_DESCRIPTION>

If the Atlassian MCP requires authentication, output exactly this line and nothing else:
AUTH_REQUIRED
"""


CODE_QA_PROMPT = """\
You are the CODE-QA stage of an automated coding harness.

Your job is to run the target repository's existing static-analysis suite
against the current working tree and report whether it passes.

Do the following, in this exact order:

1. Discover what QA tooling this repository actually has by inspecting
   (in priority order, only the ones that exist):
     - `package.json` -> `scripts` (look for `lint`, `typecheck`, `type-check`,
       `tsc`, `format:check`, `prettier:check`, `check`, `ci`)
     - `pyproject.toml` / `setup.cfg` / `tox.ini` (ruff, flake8, black, mypy,
       pyright)
     - `Makefile` (targets like `lint`, `typecheck`, `format-check`)
     - `.pre-commit-config.yaml`
     - `Gemfile` / `Rakefile` (rubocop, standardrb, sorbet)
     - `go.mod` (`go vet`, `staticcheck`, `golangci-lint`)
     - `Cargo.toml` (`cargo clippy`, `cargo fmt --check`)

2. Run ONLY the lint, typecheck, and format-check commands you discovered.
   EXPLICITLY SKIP:
     - unit tests
     - integration tests
     - end-to-end tests
     - anything that hits the network or requires running services
   If the discovered command bundles tests with lint (e.g. `npm run ci`),
   prefer the narrower individual scripts.

3. Overwrite `{code_qa_path}` with a markdown report containing:
     - a "## Tooling discovered" section listing every relevant config
       file you found and which commands you selected from each
     - a "## Commands run" section with, for each command: the exact
       command, its exit code, and a concise summary of any failures
       (file:line + the rule/error message). Truncate long output.
     - a "## Skipped" section briefly noting test suites you skipped.

4. The VERY LAST line of `{code_qa_path}` MUST be exactly one of:
     STATUS: PASS
     STATUS: FAIL

5. After writing the file, exit the agent with:
     - exit code 0 if every command you ran exited 0 (STATUS: PASS)
     - exit code 1 if any command failed (STATUS: FAIL)
   You can do this by running `exit 0` or `exit 1` in a shell tool call
   as your final action.

Rules:
- Do NOT edit any source files. The only file you may write is `{code_qa_path}`.
- If the repository has NO discoverable lint/typecheck/format tooling at
  all, write that finding to `{code_qa_path}` and exit 0 (STATUS: PASS) — there
  is nothing to enforce.
- Do NOT install new tools or add new config. Use only what's already
  declared in the repo.
"""
