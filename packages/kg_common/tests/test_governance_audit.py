"""Tests for governance compliance audit — тесты аудита управления (§10.11)."""

from __future__ import annotations

from kg_common.governance_audit import (
    GOVERNANCE_FIELDS,
    GovernanceReport,
    GovernanceViolation,
    audit_governance,
)


def test_clean_dataset_is_clean() -> None:
    report = audit_governance(
        [{"id": "d1", "domain": "domain:lab-a", "tags": ["access:public", "quality:verified"]}]
    )
    assert report.is_clean() is True
    assert report.violation_count() == 0
    assert report.checked == 1


def test_empty_domain_flags_domain() -> None:
    report = audit_governance(
        [{"id": "d2", "domain": "", "tags": ["access:public", "quality:verified"]}]
    )
    assert report.is_clean() is False
    assert report.violations[0].dataset_id == "d2"
    assert report.violations[0].missing == ("domain",)


def test_missing_domain_key_flags_domain() -> None:
    report = audit_governance([{"id": "d3", "tags": ["access:public", "quality:verified"]}])
    assert report.violations[0].missing == ("domain",)


def test_missing_access_tag_detected() -> None:
    report = audit_governance(
        [{"id": "d4", "domain": "domain:lab-a", "tags": ["quality:verified"]}]
    )
    assert report.violations[0].missing == ("access",)


def test_missing_quality_tag_detected() -> None:
    report = audit_governance([{"id": "d5", "domain": "domain:lab-a", "tags": ["access:public"]}])
    assert report.violations[0].missing == ("quality",)


def test_all_missing_ordered_subset() -> None:
    report = audit_governance([{"id": "d6", "domain": None, "tags": []}])
    assert report.violations[0].missing == ("domain", "access", "quality")
    # missing is an ordered subset of the canonical field order.
    m = report.violations[0].missing
    assert list(m) == [f for f in GOVERNANCE_FIELDS if f in m]


def test_domain_and_quality_missing_keeps_order() -> None:
    report = audit_governance([{"id": "d7", "domain": "", "tags": ["access:internal"]}])
    assert report.violations[0].missing == ("domain", "quality")


def test_checked_counts_all_including_clean() -> None:
    report = audit_governance(
        [
            {"id": "ok", "domain": "domain:x", "tags": ["access:public", "quality:pending"]},
            {"id": "bad", "domain": "", "tags": []},
        ]
    )
    assert report.checked == 2
    assert report.violation_count() == 1
    assert report.violation_count() == len(report.violations)
    assert report.violations[0].dataset_id == "bad"


def test_no_inputs_is_clean() -> None:
    report = audit_governance([])
    assert report.is_clean() is True
    assert report.checked == 0
    assert report.violation_count() == 0


def test_tags_missing_key_flags_both_facets() -> None:
    report = audit_governance([{"id": "d8", "domain": "domain:x"}])
    assert report.violations[0].missing == ("access", "quality")


def test_string_tags_not_treated_as_iterable_of_chars() -> None:
    # A bare string must not be scanned char-by-char; both facets absent.
    report = audit_governance([{"id": "d9", "domain": "domain:x", "tags": "access:public"}])
    assert report.violations[0].missing == ("access", "quality")


def test_facet_prefix_not_substring_match() -> None:
    # "no-access:x" must not satisfy the access facet.
    report = audit_governance(
        [{"id": "d10", "domain": "domain:x", "tags": ["no-access:x", "quality:verified"]}]
    )
    assert report.violations[0].missing == ("access",)


def test_violation_as_dict() -> None:
    v = GovernanceViolation(dataset_id="d1", missing=("domain", "access"))
    assert v.as_dict() == {"dataset_id": "d1", "missing": ["domain", "access"]}


def test_report_as_dict_shape() -> None:
    report = audit_governance([{"id": "d1", "domain": "", "tags": []}])
    d = report.as_dict()
    assert d == {
        "violations": [{"dataset_id": "d1", "missing": ["domain", "access", "quality"]}],
        "checked": 1,
        "violation_count": 1,
        "clean": False,
    }


def test_report_is_frozen() -> None:
    report = GovernanceReport(violations=(), checked=0)
    for attr, val in (("checked", 5), ("violations", (1,))):
        try:
            setattr(report, attr, val)
        except AttributeError:
            continue
        raise AssertionError(f"expected frozen dataclass to reject setattr on {attr}")
