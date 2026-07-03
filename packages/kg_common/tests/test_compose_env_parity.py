"""Tests for `.env.example` vs compose variable parity (§2.2).

RU: Тесты паритета переменных compose и .env.example. EN: hand-checkable parity
tests. Every expected set/tuple below is computed by eye from the tiny inputs.
"""

from __future__ import annotations

from kg_common.compose_env_parity import (
    EnvParityReport,
    compose_vars,
    env_example_keys,
    reconcile,
)


def test_compose_vars_plain_and_default_forms() -> None:
    text = "image: ${NEO4J_AUTH}\nx: ${QDRANT_URL:-http://q}"
    assert compose_vars(text) == frozenset({"NEO4J_AUTH", "QDRANT_URL"})


def test_compose_vars_error_form_is_captured() -> None:
    # ${VAR:?msg} — the name VAR is captured, the message is ignored.
    assert compose_vars("v: ${VAR:?must be set}") == frozenset({"VAR"})


def test_compose_vars_dedup_and_multiple_per_line() -> None:
    text = "a: ${A} ${B}\nb: ${A:-1}"
    assert compose_vars(text) == frozenset({"A", "B"})


def test_env_example_keys_skips_comment_and_blank() -> None:
    assert env_example_keys("# c\nA=1\nB=2") == frozenset({"A", "B"})


def test_env_example_keys_comment_line_is_skipped() -> None:
    # A '#'-prefixed line that happens to contain 'A=1' must NOT yield 'A'.
    assert env_example_keys("# A=1\nB=2") == frozenset({"B"})


def test_env_example_keys_blank_lines_ignored() -> None:
    assert env_example_keys("\n\nX=foo\n\nY=bar\n") == frozenset({"X", "Y"})


def test_reconcile_missing_when_env_lacks_var() -> None:
    report = reconcile("v: ${X}", "Y=1")
    assert report.missing == ("X",)
    assert report.ok is False


def test_reconcile_unused_when_key_not_referenced() -> None:
    # Compose uses X (declared); Y is declared but never referenced -> unused.
    report = reconcile("v: ${X}", "X=1\nY=2")
    assert report.missing == ()
    assert report.unused == ("Y",)
    assert report.ok is True


def test_reconcile_both_sorted() -> None:
    report = reconcile("a: ${B} ${A}", "D=1\nC=2")
    assert report.missing == ("A", "B")
    assert report.unused == ("C", "D")
    assert report.ok is False


def test_reconcile_full_parity() -> None:
    report = reconcile("a: ${A}\nb: ${B:-x}", "A=1\nB=2")
    assert report == EnvParityReport(missing=(), unused=(), ok=True)


def test_as_dict_ok_is_bool() -> None:
    report = reconcile("v: ${X}", "X=1")
    d = report.as_dict()
    assert d == {"missing": [], "unused": [], "ok": True}
    assert isinstance(d["ok"], bool)


def test_report_is_frozen() -> None:
    report = reconcile("v: ${X}", "X=1")
    try:
        report.ok = False  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("EnvParityReport must be frozen")
