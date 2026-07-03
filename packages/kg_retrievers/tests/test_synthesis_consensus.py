"""Tests for synthesis-level consensus vs disagreement (§24.11)."""

from __future__ import annotations

from kg_retrievers.synthesis_consensus import ClaimGroup, group_claims, is_consensus


def _claim(pid: str, value: float, source_id: str) -> dict:
    return {"property_id": pid, "value": value, "source_id": source_id}


def test_single_source_is_single() -> None:
    groups = group_claims([_claim("p", 10.0, "s1")])
    assert len(groups) == 1
    g = groups[0]
    assert g.verdict == "single"
    assert g.n_independent == 1
    assert g.source_ids == ("s1",)
    assert g.value_min == 10.0 and g.value_max == 10.0


def test_two_distinct_sources_equal_is_consensus() -> None:
    groups = group_claims([_claim("p", 42.0, "s1"), _claim("p", 42.0, "s2")])
    g = groups[0]
    assert g.verdict == "consensus"
    assert g.n_independent == 2
    assert g.source_ids == ("s1", "s2")


def test_two_distinct_sources_wide_is_disagreement() -> None:
    groups = group_claims([_claim("p", 10.0, "s1"), _claim("p", 30.0, "s2")])
    g = groups[0]
    assert g.verdict == "disagreement"
    assert g.n_independent == 2
    assert g.value_min == 10.0 and g.value_max == 30.0


def test_duplicate_same_source_counts_once() -> None:
    # Two claims but one distinct source -> still 'single'.
    groups = group_claims([_claim("p", 10.0, "s1"), _claim("p", 10.0, "s1")])
    g = groups[0]
    assert g.n_independent == 1
    assert g.verdict == "single"
    assert g.source_ids == ("s1",)


def test_duplicate_source_does_not_manufacture_consensus() -> None:
    # s1 appears twice, s2 once -> 2 independent, tight values -> consensus.
    groups = group_claims(
        [_claim("p", 10.0, "s1"), _claim("p", 10.0, "s1"), _claim("p", 10.2, "s2")]
    )
    g = groups[0]
    assert g.n_independent == 2
    assert g.verdict == "consensus"


def test_rel_tol_boundary_consensus() -> None:
    # (104 - 100) / 104 = 0.0385 <= 0.05 -> consensus.
    groups = group_claims([_claim("p", 100.0, "s1"), _claim("p", 104.0, "s2")])
    assert groups[0].verdict == "consensus"


def test_rel_tol_boundary_disagreement() -> None:
    # (110 - 100) / 110 = 0.0909 > 0.05 -> disagreement.
    groups = group_claims([_claim("p", 100.0, "s1"), _claim("p", 110.0, "s2")])
    assert groups[0].verdict == "disagreement"


def test_value_min_max_span_group() -> None:
    groups = group_claims(
        [
            _claim("p", 5.0, "s1"),
            _claim("p", 9.0, "s2"),
            _claim("p", 7.0, "s3"),
        ]
    )
    g = groups[0]
    assert g.value_min == 5.0
    assert g.value_max == 9.0


def test_empty_claims_returns_empty() -> None:
    assert group_claims([]) == []


def test_multiple_properties_preserve_order() -> None:
    groups = group_claims(
        [
            _claim("beta", 1.0, "s1"),
            _claim("alpha", 2.0, "s1"),
            _claim("alpha", 2.0, "s2"),
        ]
    )
    assert [g.property_id for g in groups] == ["beta", "alpha"]
    assert groups[0].verdict == "single"
    assert groups[1].verdict == "consensus"


def test_is_consensus_direct() -> None:
    assert is_consensus([100.0, 104.0], ["s1", "s2"]) is True
    assert is_consensus([100.0, 110.0], ["s1", "s2"]) is False
    # Not enough distinct sources.
    assert is_consensus([100.0, 100.0], ["s1", "s1"]) is False
    # min_sources override.
    assert is_consensus([1.0, 1.0, 1.0], ["a", "b", "c"], min_sources=3) is True
    assert is_consensus([1.0, 1.0], ["a", "b"], min_sources=3) is False
    # Empty inputs.
    assert is_consensus([], []) is False


def test_as_dict_shape() -> None:
    g = ClaimGroup(
        property_id="p",
        verdict="consensus",
        source_ids=("s1", "s2"),
        n_independent=2,
        value_min=1.0,
        value_max=2.0,
    )
    assert g.as_dict() == {
        "property_id": "p",
        "verdict": "consensus",
        "source_ids": ["s1", "s2"],
        "n_independent": 2,
        "value_min": 1.0,
        "value_max": 2.0,
    }


def test_frozen_dataclass_immutable() -> None:
    g = group_claims([_claim("p", 1.0, "s1")])[0]
    try:
        g.verdict = "disagreement"  # type: ignore[misc]
    except Exception as exc:  # dataclasses.FrozenInstanceError
        assert "frozen" in type(exc).__name__.lower() or "cannot assign" in str(exc)
    else:
        raise AssertionError("ClaimGroup should be immutable")
