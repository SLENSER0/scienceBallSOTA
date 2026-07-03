"""§10.6 tests — Lab→Domain grouping: build, lookup, assign, dedup.

RU: Тесты группировки Lab→Domain (§10.6). EN: Tests for Lab→Domain grouping.
"""

from __future__ import annotations

from kg_common.metadata.domains import (
    Domain,
    assign_asset,
    build_domains,
    domain_for_lab,
)


def test_build_domains_basic() -> None:
    ds = build_domains([{"id": "lab-a", "name": "Lab A"}, {"id": "lab-b", "name": "Lab B"}])
    assert len(ds) == 2
    assert ds[0].key == "lab-a"
    assert ds[0].name == "Lab A"
    assert ds[0].lab_id == "lab-a"
    assert ds[0].urn() == "urn:li:domain:lab-a"
    assert ds[1].key == "lab-b"


def test_build_domains_sorted_by_key() -> None:
    ds = build_domains([{"id": "lab-z", "name": "Z"}, {"id": "lab-a", "name": "A"}])
    assert [d.key for d in ds] == ["lab-a", "lab-z"]


def test_build_domains_dedup_on_key() -> None:
    ds = build_domains([{"id": "x", "name": "X"}, {"id": "x", "name": "X2"}])
    assert len(ds) == 1
    # First occurrence wins.
    assert ds[0].name == "X"


def test_domain_for_lab_found_and_missing() -> None:
    ds = build_domains([{"id": "lab-a", "name": "Lab A"}, {"id": "lab-b", "name": "Lab B"}])
    found = domain_for_lab(ds, "lab-b")
    assert found is not None
    assert found.name == "Lab B"
    assert domain_for_lab(ds, "missing") is None


def test_assign_asset_found_and_missing() -> None:
    ds = build_domains([{"id": "lab-a", "name": "Lab A"}, {"id": "lab-b", "name": "Lab B"}])
    assigned = assign_asset(ds, "lab-a")
    assert assigned is not None
    assert assigned.key == "lab-a"
    assert assign_asset(ds, "nope") is None


def test_as_dict_shape() -> None:
    d = Domain(key="lab-a", name="Lab A", lab_id="lab-a")
    assert d.as_dict() == {
        "key": "lab-a",
        "name": "Lab A",
        "lab_id": "lab-a",
        "urn": "urn:li:domain:lab-a",
    }


def test_domain_is_frozen() -> None:
    d = Domain(key="k", name="n", lab_id="l")
    try:
        d.key = "other"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Domain must be frozen")
