"""Atlassian MCP integration: fetch Jira issues via cursor-agent."""

from __future__ import annotations

import re
from pathlib import Path

from harness.infrastructure.cursor_agent import run_agent_ephemeral
from harness.logging import die, log
from harness.prompts import JIRA_FETCH_PROMPT

_TASK_RE = re.compile(r"<TASK_DESCRIPTION>\s*(.*?)\s*</TASK_DESCRIPTION>", re.DOTALL)


def _parse_task_description(text: str) -> str | None:
    m = _TASK_RE.search(text)
    return m.group(1).strip() if m else None


def fetch_jira_task(url: str, *, model: str, repo: Path) -> str:
    """Fetch a Jira issue and return its task description string.

    Retries once after prompting the user to authenticate if the
    Atlassian MCP reports AUTH_REQUIRED.
    """
    for attempt in range(2):
        code, text = run_agent_ephemeral(
            JIRA_FETCH_PROMPT.format(url=url),
            cwd=repo,
            model=model,
        )
        if "AUTH_REQUIRED" in text:
            if attempt == 0:
                log("Atlassian MCP requires authentication.")
                log("Please complete the login process in your browser or terminal.")
                input("[harness] Press Enter once you have finished logging in... ")
                continue
            die("Atlassian authentication failed after retry. Aborting.")

        task = _parse_task_description(text)
        if task:
            return task

        if code != 0:
            die(f"cursor-agent exited with code {code} while fetching {url!r}.")

        die(
            f"Could not parse a task description from the agent response "
            f"for {url!r}. Check the output above for details."
        )

    # Unreachable but makes type-checkers happy.
    die("Failed to fetch Jira task.")
    raise RuntimeError  # never reached
