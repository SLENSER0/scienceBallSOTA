"""Tests for findings-to-member mention coverage (§11.4)."""

from __future__ import annotations

from kg_retrievers.community_findings_member_coverage import (
    FindingsCoverage,
    findings_member_coverage,
)


def test_basic_coverage() -> None:
    members = ["Titanium", "Nickel", "Cobalt"]
    text = "Titanium alloys outperform nickel baselines."
    cov = findings_member_coverage(members, text)

    assert cov.n_members == 3
    assert cov.n_covered == 2  # Titanium (exact) + nickel (case-insensitive)
    assert abs(cov.coverage - 2 / 3) < 1e-9
    assert cov.uncovered_members == ("Cobalt",)
    assert cov.as_dict()["n_covered"] == 2


def test_no_members() -> None:
    cov = findings_member_coverage([], "x")
    assert cov.coverage == 0.0
    assert cov.n_members == 0


def test_empty_text() -> None:
    assert findings_member_coverage(["Ti"], "").n_covered == 0


def test_frozen_and_as_dict_roundtrip() -> None:
    cov = findings_member_coverage(["Iron"], "Iron oxides form readily.")
    assert isinstance(cov, FindingsCoverage)
    d = cov.as_dict()
    assert d == {
        "n_members": 1,
        "n_covered": 1,
        "coverage": 1.0,
        "uncovered_members": [],
    }
