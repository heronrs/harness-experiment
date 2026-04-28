"""Parse the ``STATUS: PASS`` / ``STATUS: FAIL`` trailer from agent reports.

Both the reviewer and code-qa stages instruct the agent to end its
markdown report with one of those two literal lines. The agent's
process exit code is unreliable (the LLM does not always honor the
"exit 1 on FAIL" instruction), so we parse the trailer from the file
itself and treat that as the source of truth.

This module is intentionally pure (no I/O beyond reading the report
file the caller already has in hand) so it can be unit-tested without
fixtures.
"""

from __future__ import annotations

from pathlib import Path

from harness.logging import die, warn

_PASS = "STATUS: PASS"
_FAIL = "STATUS: FAIL"


def parse_status_trailer(report_path: Path) -> bool:
    """Return ``True`` for PASS, ``False`` for FAIL.

    The trailer is the last non-empty, stripped line of the file. If
    the file is missing or the trailer is absent/malformed, this
    ``die()``s — the prompt requires the trailer, and silently
    treating a missing trailer as either verdict would re-introduce
    the bug this helper exists to prevent.
    """
    if not report_path.exists():
        die(f"report file does not exist: {report_path}")
    lines = [line.strip() for line in report_path.read_text().splitlines()]
    last = next((line for line in reversed(lines) if line), "")
    if last == _PASS:
        return True
    if last == _FAIL:
        return False
    die(
        f"{report_path} is missing a 'STATUS: PASS' or 'STATUS: FAIL' "
        f"trailer (last non-empty line was: {last!r})"
    )
    raise AssertionError("unreachable")  # for type-checkers: die() does not return


def reconcile_with_exit_code(
    *, report_path: Path, exit_code: int, stage: str, iteration: int
) -> bool:
    """Return the verdict from the report, warning on disagreement.

    The report's trailer is authoritative. The agent's exit code is
    only used to surface diagnostic warnings when the two disagree
    (which usually means the agent forgot to ``exit 1`` on FAIL, or
    crashed after writing PASS).
    """
    passed = parse_status_trailer(report_path)
    expected_code = 0 if passed else 1
    if exit_code != expected_code:
        verdict = "PASS" if passed else "FAIL"
        warn(
            f"{stage} iteration {iteration}: trailer says {verdict} but "
            f"agent exited {exit_code} (expected {expected_code}). "
            "Trusting the trailer."
        )
    return passed
