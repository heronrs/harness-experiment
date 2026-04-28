"""Unit tests for the STATUS trailer parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.services.status_trailer import (
    parse_status_trailer,
    reconcile_with_exit_code,
)


def test_parse_pass(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("# review\n\nlooks good\n\nSTATUS: PASS\n")
    assert parse_status_trailer(p) is True


def test_parse_fail(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("# review\n\nbroken\n\nSTATUS: FAIL\n")
    assert parse_status_trailer(p) is False


def test_parse_ignores_trailing_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("body\nSTATUS: FAIL\n\n\n   \n")
    assert parse_status_trailer(p) is False


def test_parse_missing_trailer_dies(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("# review\n\nno trailer here\n")
    with pytest.raises(SystemExit):
        parse_status_trailer(p)


def test_parse_malformed_trailer_dies(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("body\nstatus: pass\n")
    with pytest.raises(SystemExit):
        parse_status_trailer(p)


def test_parse_missing_file_dies(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        parse_status_trailer(tmp_path / "missing.md")


def test_reconcile_agreement_pass(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("STATUS: PASS\n")
    assert (
        reconcile_with_exit_code(
            report_path=p, exit_code=0, stage="reviewer", iteration=1
        )
        is True
    )


def test_reconcile_disagreement_trailer_wins(tmp_path: Path) -> None:
    """The bug we're fixing: agent wrote FAIL but exited 0."""
    p = tmp_path / "r.md"
    p.write_text("STATUS: FAIL\n")
    assert (
        reconcile_with_exit_code(
            report_path=p, exit_code=0, stage="reviewer", iteration=1
        )
        is False
    )


def test_reconcile_pass_trailer_with_nonzero_exit(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("STATUS: PASS\n")
    assert (
        reconcile_with_exit_code(
            report_path=p, exit_code=2, stage="code-qa", iteration=3
        )
        is True
    )
