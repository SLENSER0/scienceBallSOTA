"""Tests for §11.2/§11.4 community-report token-budget trimming.

Hand-checkable: with ``chars_per_token=4`` каждая оценка токенов равна
``len(text) // 4``, поэтому все бюджеты считаются вручную.
"""

from __future__ import annotations

from kg_retrievers.community_report_trim import (
    TrimmedReport,
    estimate_tokens,
    trim_report,
)


def test_estimate_tokens_floor_division() -> None:
    # 'abcdefgh' -> 8 chars // 4 == 2 (spec assertion).
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 0  # 3 // 4
    assert estimate_tokens("abcdefgh", chars_per_token=2) == 4


def test_small_report_under_budget_keeps_all_findings() -> None:
    report = {
        "community_id": 7,
        "title": "T",
        "summary": "S",
        "findings": [{"summary": "one"}, {"summary": "two"}],
    }
    result = trim_report(report, max_tokens=1000)
    assert result.truncated is False
    assert result.kept_findings == len(report["findings"])
    assert result.kept_findings == 2


def test_title_and_summary_always_present() -> None:
    report = {"title": "MyTitle", "summary": "MySummary", "findings": []}
    result = trim_report(report, max_tokens=1000)
    assert result.text.startswith("MyTitle")
    assert "MySummary" in result.text
    # Zero findings -> nothing kept, nothing dropped.
    assert result.kept_findings == 0
    assert result.truncated is False


def test_overflow_drops_trailing_findings() -> None:
    # text0 = "AB\nCD" -> 5 chars // 4 == 1 token.
    # +"\nEEEE" -> 10 chars // 4 == 2 tokens (fits at max_tokens=3).
    # +"\nFFFF" -> 15 chars // 4 == 3 tokens (fits).
    # +"\nGGGG" -> 20 chars // 4 == 5 tokens (overflows) -> dropped.
    report = {
        "community_id": 3,
        "title": "AB",
        "summary": "CD",
        "findings": [
            {"summary": "EEEE"},
            {"summary": "FFFF"},
            {"summary": "GGGG"},
        ],
    }
    result = trim_report(report, max_tokens=3)
    assert result.truncated is True
    assert result.kept_findings == 2  # only the first two lines fit
    assert result.est_tokens == 3
    assert "GGGG" not in result.text
    assert "EEEE" in result.text and "FFFF" in result.text
    # Title and summary survive trimming.
    assert result.text.startswith("AB")
    assert "CD" in result.text


def test_est_tokens_matches_len_over_four() -> None:
    report = {
        "community_id": 1,
        "title": "Header",
        "summary": "Body text here",
        "findings": [{"summary": "finding alpha"}, {"summary": "finding beta"}],
    }
    result = trim_report(report, max_tokens=1000)
    assert result.est_tokens == len(result.text) // 4


def test_kept_findings_counts_only_fitting_lines() -> None:
    # Budget lets exactly one finding through.
    # "X\nY" -> 3 // 4 == 0; +"\nZZZZ" -> 8 // 4 == 2; +"\nWWWW" -> 13 // 4 == 3.
    report = {
        "title": "X",
        "summary": "Y",
        "findings": [{"summary": "ZZZZ"}, {"summary": "WWWW"}],
    }
    result = trim_report(report, max_tokens=2)
    assert result.kept_findings == 1
    assert result.truncated is True
    assert "ZZZZ" in result.text
    assert "WWWW" not in result.text


def test_identical_calls_return_equal_dataclasses() -> None:
    report = {
        "community_id": 42,
        "title": "Same",
        "summary": "Same summary",
        "findings": [{"summary": "aaaa"}, {"summary": "bbbb"}],
    }
    first = trim_report(report, max_tokens=50)
    second = trim_report(report, max_tokens=50)
    assert first == second
    assert isinstance(first, TrimmedReport)


def test_as_dict_round_trips_fields() -> None:
    report = {
        "community_id": 9,
        "title": "Ttl",
        "summary": "Smry",
        "findings": [{"summary": "f1"}],
    }
    result = trim_report(report, max_tokens=1000)
    d = result.as_dict()
    assert d == {
        "community_id": 9,
        "text": result.text,
        "est_tokens": result.est_tokens,
        "truncated": False,
        "kept_findings": 1,
    }


def test_bare_string_findings_supported() -> None:
    report = {
        "community_id": 5,
        "title": "T",
        "summary": "S",
        "findings": ["plain finding line"],
    }
    result = trim_report(report, max_tokens=1000)
    assert result.kept_findings == 1
    assert "plain finding line" in result.text
