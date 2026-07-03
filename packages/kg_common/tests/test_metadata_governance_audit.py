"""Tests for the dataset governance-completeness audit (§10.11)."""

from __future__ import annotations

from kg_common.metadata.governance_audit import (
    GovernanceReport,
    GovernanceViolation,
    audit_governance,
)


def test_fully_tagged_asset_no_violation() -> None:
    report = audit_governance([{"asset_id": "a", "owner": "x", "domain": "d", "access": "public"}])
    assert report.n_violations == 0
    assert report.n_ok == 1
    assert report.violations == ()


def test_blank_owner_is_missing() -> None:
    report = audit_governance([{"asset_id": "b", "owner": "", "domain": "d", "access": "public"}])
    assert report.n_violations == 1
    assert report.violations[0].asset_id == "b"
    assert report.violations[0].missing == ("owner",)


def test_all_tags_absent_sorted_missing() -> None:
    report = audit_governance([{"asset_id": "c"}])
    assert report.violations[0].missing == ("access", "domain", "owner")
    assert report.n_ok == 0
    assert report.n_violations == 1


def test_whitespace_only_tag_is_missing() -> None:
    report = audit_governance([{"asset_id": "w", "owner": "  ", "domain": "d", "access": "public"}])
    assert report.violations[0].missing == ("owner",)


def test_two_asset_mix_counts() -> None:
    report = audit_governance(
        [
            {"asset_id": "ok", "owner": "x", "domain": "d", "access": "public"},
            {"asset_id": "bad", "owner": "y", "domain": "d"},  # access absent
        ]
    )
    assert report.n_ok == 1
    assert report.n_violations == 1
    assert report.violations[0].asset_id == "bad"
    assert report.violations[0].missing == ("access",)


def test_violations_sorted_by_asset_id() -> None:
    report = audit_governance(
        [
            {"asset_id": "z"},
            {"asset_id": "m"},
            {"asset_id": "a"},
        ]
    )
    assert [v.asset_id for v in report.violations] == ["a", "m", "z"]


def test_violation_as_dict_round_trippable() -> None:
    as_dict = GovernanceViolation("c", ("owner",)).as_dict()
    assert as_dict["asset_id"] == "c"
    assert as_dict["missing"] in (["owner"], ("owner",))


def test_report_as_dict_expands_violations() -> None:
    report = audit_governance([{"asset_id": "c"}])
    as_dict = report.as_dict()
    assert as_dict["n_ok"] == 0
    assert as_dict["n_violations"] == 1
    first = as_dict["violations"][0]
    assert first["asset_id"] == "c"
    assert list(first["missing"]) == ["access", "domain", "owner"]


def test_custom_required_ignores_domain() -> None:
    report = audit_governance(
        [{"asset_id": "d", "owner": "x"}],  # no domain, no access
        required=("owner",),
    )
    assert report.n_violations == 0
    assert report.n_ok == 1


def test_custom_required_still_flags_missing_owner() -> None:
    report = audit_governance(
        [{"asset_id": "d", "domain": "d"}],  # owner absent
        required=("owner",),
    )
    assert report.violations[0].missing == ("owner",)


def test_empty_input() -> None:
    report = audit_governance([])
    assert report.n_ok == 0
    assert report.n_violations == 0
    assert report.violations == ()


def test_frozen_dataclasses() -> None:
    report = audit_governance([{"asset_id": "c"}])
    assert isinstance(report, GovernanceReport)
    import dataclasses

    for frozen in (report, report.violations[0]):
        try:
            frozen.n_ok = 5  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            pass
        else:  # pragma: no cover - guard only
            raise AssertionError("expected frozen dataclass")
