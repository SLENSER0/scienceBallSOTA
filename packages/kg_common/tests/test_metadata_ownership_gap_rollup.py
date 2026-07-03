"""Tests for §10.6 ownership / governance gap rollup by lab (Gap Dashboard §5.2.7).

Hand-checkable assertions over pure functions — no store, no I/O (детерминированно).
"""

from __future__ import annotations

from kg_common.metadata.ownership_gap_rollup import (
    LabGap,
    rollup_by_lab,
    total_gaps,
    worst_lab,
)


def _asset(asset_id: str, lab: str, owner: str | None = "u", domain: str | None = "d"):
    """Build an asset mapping; pass ``None`` to omit an owner/domain tag."""
    a: dict[str, object] = {"asset_id": asset_id, "lab": lab}
    if owner is not None:
        a["owner"] = owner
    if domain is not None:
        a["domain"] = domain
    return a


def test_empty_rollup_is_empty() -> None:
    assert rollup_by_lab([]) == []


def test_complete_asset_has_zero_gap() -> None:
    rollup = rollup_by_lab([_asset("a1", "alpha")])
    assert len(rollup) == 1
    row = rollup[0]
    assert row.lab == "alpha"
    assert row.total == 1
    assert row.missing_owner == 0
    assert row.missing_domain == 0
    assert row.gap_count == 0


def test_missing_owner_counts_as_one_gap() -> None:
    rollup = rollup_by_lab([_asset("a1", "alpha", owner=None)])
    row = rollup[0]
    assert row.missing_owner == 1
    assert row.missing_domain == 0
    assert row.gap_count == 1


def test_same_lab_pair_one_complete_one_missing() -> None:
    rollup = rollup_by_lab([_asset("a1", "alpha"), _asset("a2", "alpha", owner="  ")])
    assert len(rollup) == 1
    row = rollup[0]
    assert row.total == 2
    assert row.missing_owner == 1  # whitespace owner counts as missing
    assert row.gap_count == 1


def test_blank_lab_bucketed_under_unassigned() -> None:
    rollup = rollup_by_lab([_asset("a1", "")])
    assert rollup[0].lab == "__unassigned__"
    # absent lab key too
    rollup2 = rollup_by_lab([{"asset_id": "a2", "owner": "u", "domain": "d"}])
    assert rollup2[0].lab == "__unassigned__"


def test_sort_more_gaps_before_fewer() -> None:
    assets = [
        _asset("b1", "beta", owner=None),
        _asset("b2", "beta", domain=None),
        _asset("a1", "alpha", owner=None),
    ]
    rollup = rollup_by_lab(assets)
    assert [r.lab for r in rollup] == ["beta", "alpha"]
    assert rollup[0].gap_count == 2
    assert rollup[1].gap_count == 1


def test_sort_tie_breaks_by_lab_ascending() -> None:
    assets = [_asset("z1", "zeta", owner=None), _asset("a1", "alpha", owner=None)]
    rollup = rollup_by_lab(assets)
    assert [r.lab for r in rollup] == ["alpha", "zeta"]


def test_total_gaps_sums_across_labs() -> None:
    assets = [
        _asset("b1", "beta", owner=None),
        _asset("b2", "beta", domain=None),
        _asset("a1", "alpha", owner=None),
        _asset("a2", "alpha"),
    ]
    rollup = rollup_by_lab(assets)
    assert total_gaps(rollup) == 3


def test_worst_lab_returns_most_gapped() -> None:
    assets = [
        _asset("b1", "beta", owner=None),
        _asset("b2", "beta", domain=None),
        _asset("a1", "alpha", owner=None),
    ]
    assert worst_lab(rollup_by_lab(assets)) == "beta"


def test_worst_lab_none_when_all_zero() -> None:
    rollup = rollup_by_lab([_asset("a1", "alpha"), _asset("b1", "beta")])
    assert all(r.gap_count == 0 for r in rollup)
    assert worst_lab(rollup) is None


def test_worst_lab_tie_breaks_lexicographically() -> None:
    assets = [_asset("z1", "zeta", owner=None), _asset("a1", "alpha", owner=None)]
    assert worst_lab(rollup_by_lab(assets)) == "alpha"


def test_labgap_as_dict_roundtrip() -> None:
    row = LabGap(lab="alpha", total=2, missing_owner=1, missing_domain=0, gap_count=1)
    assert row.as_dict() == {
        "lab": "alpha",
        "total": 2,
        "missing_owner": 1,
        "missing_domain": 0,
        "gap_count": 1,
    }


def test_required_narrowing_ignores_domain() -> None:
    # asset missing only domain, but required=('owner',) → no gap
    rollup = rollup_by_lab([_asset("a1", "alpha", domain=None)], required=("owner",))
    row = rollup[0]
    assert row.missing_domain == 1  # tracked regardless of required
    assert row.gap_count == 0  # domain not required here
