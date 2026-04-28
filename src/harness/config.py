"""Centralized configuration constants."""

from __future__ import annotations

from pathlib import Path

DEFAULT_MODEL = "claude-4.6-sonnet-medium-thinking"
MAX_REVIEW_ITERATIONS = 3
MAX_CODE_QA_ITERATIONS = 3
AGENT_TIMEOUT_SECONDS = 15 * 60

HARNESS_DIR = Path(".harness")
LOGS_DIR = HARNESS_DIR / "logs"

BASE_BRANCH = "main"
