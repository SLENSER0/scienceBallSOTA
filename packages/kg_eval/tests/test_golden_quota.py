"""Tests for the golden dataset category quota validator (§18.6)."""

from __future__ import annotations

from kg_eval.golden_quota import (
    REQUIRED_QUOTAS,
    QuotaReport,
    check_quota,
    count_categories,
)


def _exact_quota_items() -> list[dict[str, str]]:
    """Build a 75-item set that hits every §15.1 quota exactly, unique ids."""
    items: list[dict[str, str]] = []
    n = 0
    for category, quota in REQUIRED_QUOTAS.items():
        for _ in range(quota):
            items.append({"id": f"q{n}", "category": category})
            n += 1
    return items


def test_exact_quota_set_is_ok() -> None:
    items = _exact_quota_items()
    assert len(items) == 75
    report = check_quota(items)
    assert report.ok is True
    assert report.missing == ()
    assert report.duplicate_ids == ()
    assert report.surplus == {}


def test_one_category_short_by_one_is_missing() -> None:
    items = _exact_quota_items()
    # Drop one evidence item -> evidence has 9 of 10.
    for i, item in enumerate(items):
        if item["category"] == "evidence":
            del items[i]
            break
    report = check_quota(items)
    assert "evidence" in report.missing
    assert report.ok is False


def test_duplicate_id_populates_duplicate_ids() -> None:
    items = _exact_quota_items()
    # Force a repeated id while keeping category counts on quota.
    items[5]["id"] = items[0]["id"]
    report = check_quota(items)
    assert items[0]["id"] in report.duplicate_ids
    assert report.ok is False


def test_surplus_counted_but_does_not_fail_ok() -> None:
    items = _exact_quota_items()
    items.append({"id": "extra_mrp", "category": "material_regime_property"})
    report = check_quota(items)
    assert report.surplus == {"material_regime_property": 1}
    # 21 vs 20 is a surplus, not a shortfall — ok stays True.
    assert report.missing == ()
    assert report.duplicate_ids == ()
    assert report.ok is True


def test_count_categories_tallies_unknown_category() -> None:
    items = [
        {"id": "a", "category": "evidence"},
        {"id": "b", "category": "evidence"},
        {"id": "c", "category": "totally_unknown"},
    ]
    counts = count_categories(items)
    assert counts == {"evidence": 2, "totally_unknown": 1}


def test_empty_input_marks_all_quota_categories_missing() -> None:
    report = check_quota([])
    assert set(report.missing) == set(REQUIRED_QUOTAS)
    assert report.counts == {}
    assert report.duplicate_ids == ()
    assert report.ok is False


def test_as_dict_ok_is_bool() -> None:
    report = check_quota(_exact_quota_items())
    d = report.as_dict()
    assert isinstance(d["ok"], bool)
    assert d["ok"] is True
    assert isinstance(report, QuotaReport)
