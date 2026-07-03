"""Tests for the absence-map entropy KPI (§25.11).

Hand-checkable Shannon-entropy cases over verdict distributions: uniform coverage (zero
entropy), a balanced two-status split (one bit / fully normalized), single-category maps,
alphabetical tie-breaking, and the empty map.
"""

from __future__ import annotations

from kg_retrievers.absence_map_entropy import MapEntropy, map_entropy


def _cells(statuses: list[str]) -> list[dict]:
    """Build a flat absence map from a list of status tokens."""
    return [{"status": s} for s in statuses]


def test_all_covered_zero_entropy() -> None:
    result = map_entropy(_cells(["COVERED", "COVERED", "COVERED", "COVERED"]))
    assert result.n_cells == 4
    assert result.entropy_bits == 0.0
    assert result.normalized == 0.0
    assert result.dominant_status == "COVERED"


def test_two_covered_two_gap_one_bit() -> None:
    result = map_entropy(_cells(["COVERED", "COVERED", "GAP", "GAP"]))
    assert result.entropy_bits == 1.0
    assert result.normalized == 1.0
    assert result.counts == {"COVERED": 2, "GAP": 2}


def test_single_category_normalized_zero() -> None:
    result = map_entropy(_cells(["GAP", "GAP", "GAP"]))
    assert result.normalized == 0.0
    assert result.entropy_bits == 0.0
    assert result.dominant_status == "GAP"


def test_alphabetical_tie_break() -> None:
    result = map_entropy(_cells(["B", "A"]))
    assert result.dominant_status == "A"
    assert result.entropy_bits == 1.0


def test_empty_input() -> None:
    result = map_entropy([])
    assert result.n_cells == 0
    assert result.entropy_bits == 0.0
    assert result.normalized == 0.0
    assert result.dominant_status == ""


def test_missing_status_key_bucketed_unknown() -> None:
    result = map_entropy([{"status": "COVERED"}, {}])
    assert result.counts == {"COVERED": 1, "unknown": 1}
    assert result.entropy_bits == 1.0


def test_custom_status_key() -> None:
    cells = [{"verdict": "COVERED"}, {"verdict": "GAP"}]
    result = map_entropy(cells, status_key="verdict")
    assert result.counts == {"COVERED": 1, "GAP": 1}
    assert result.entropy_bits == 1.0


def test_as_dict_counts_is_dict() -> None:
    result = map_entropy(_cells(["COVERED", "GAP"]))
    payload = result.as_dict()
    assert isinstance(payload["counts"], dict)
    assert isinstance(result, MapEntropy)
    assert payload["dominant_status"] == "COVERED"
