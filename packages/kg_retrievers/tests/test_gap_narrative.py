"""Tests for §24.11 answer blocks 'что неизвестно' / 'что проверить пилотно'."""

from __future__ import annotations

from kg_retrievers.gap_narrative import GapBlocks, build_gap_blocks


def test_zero_evidence_goes_to_unknown_only() -> None:
    """evidence_count 0 -> in unknown, absent from pilot_check."""
    blocks = build_gap_blocks([{"label": "A", "evidence_count": 0, "confidence": 0.9}])
    assert blocks.unknown == ("A",)
    assert "A" not in blocks.pilot_check
    assert blocks.pilot_check == ()


def test_low_confidence_covered_cell_goes_to_pilot() -> None:
    """evidence_count 2 confidence 0.3 -> pilot_check, not unknown."""
    blocks = build_gap_blocks([{"label": "B", "evidence_count": 2, "confidence": 0.3}])
    assert blocks.pilot_check == ("B",)
    assert blocks.unknown == ()


def test_well_covered_high_confidence_cell_in_neither() -> None:
    """evidence_count 2 confidence 0.9 local_dependence False -> neither block."""
    blocks = build_gap_blocks(
        [{"label": "C", "evidence_count": 2, "confidence": 0.9, "local_dependence": False}]
    )
    assert blocks.unknown == ()
    assert blocks.pilot_check == ()


def test_local_dependence_forces_pilot_despite_high_confidence() -> None:
    """local_dependence True with high confidence -> pilot_check."""
    blocks = build_gap_blocks(
        [{"label": "D", "evidence_count": 5, "confidence": 0.95, "local_dependence": True}]
    )
    assert blocks.pilot_check == ("D",)
    assert blocks.unknown == ()


def test_duplicate_labels_collapse_and_sort() -> None:
    """Duplicate labels collapse; blocks are deduped and sorted."""
    cells = [
        {"label": "z", "evidence_count": 0},
        {"label": "z", "evidence_count": 0},
        {"label": "a", "evidence_count": 0},
        {"label": "m", "evidence_count": 3, "confidence": 0.1},
        {"label": "m", "evidence_count": 3, "confidence": 0.1},
    ]
    blocks = build_gap_blocks(cells)
    assert blocks.unknown == ("a", "z")
    assert blocks.pilot_check == ("m",)


def test_confidence_exactly_at_boundary_is_not_pilot() -> None:
    """confidence == pilot_conf (0.5) -> not pilot (strict <)."""
    blocks = build_gap_blocks(
        [{"label": "E", "evidence_count": 2, "confidence": 0.5}], pilot_conf=0.5
    )
    assert blocks.pilot_check == ()
    assert blocks.unknown == ()


def test_local_dependence_defaults_false() -> None:
    """Omitted local_dependence defaults to False -> high-confidence cell is clean."""
    blocks = build_gap_blocks([{"label": "F", "evidence_count": 4, "confidence": 0.8}])
    assert blocks.unknown == ()
    assert blocks.pilot_check == ()


def test_empty_cells_yields_empty_blocks() -> None:
    """Empty input -> both tuples empty."""
    blocks = build_gap_blocks([])
    assert blocks == GapBlocks(unknown=(), pilot_check=())
    assert blocks.unknown == ()
    assert blocks.pilot_check == ()


def test_as_dict_exposes_both_lists() -> None:
    """as_dict() exposes 'unknown' and 'pilot_check' as lists."""
    blocks = build_gap_blocks(
        [
            {"label": "u", "evidence_count": 0},
            {"label": "p", "evidence_count": 2, "confidence": 0.2},
        ]
    )
    d = blocks.as_dict()
    assert d == {"unknown": ["u"], "pilot_check": ["p"]}
    assert isinstance(d["unknown"], list)
    assert isinstance(d["pilot_check"], list)


def test_custom_pilot_conf_threshold() -> None:
    """A higher pilot_conf widens the pilot band."""
    cells = [{"label": "G", "evidence_count": 2, "confidence": 0.7}]
    assert build_gap_blocks(cells, pilot_conf=0.5).pilot_check == ()
    assert build_gap_blocks(cells, pilot_conf=0.8).pilot_check == ("G",)


def test_mixed_cells_partition_correctly() -> None:
    """A realistic mix lands each cell in the right block."""
    cells = [
        {"label": "no_exp", "evidence_count": 0, "confidence": 0.9},
        {"label": "weak_conf", "evidence_count": 3, "confidence": 0.2},
        {"label": "local", "evidence_count": 4, "confidence": 0.9, "local_dependence": True},
        {"label": "solid", "evidence_count": 6, "confidence": 0.95},
    ]
    blocks = build_gap_blocks(cells)
    assert blocks.unknown == ("no_exp",)
    assert blocks.pilot_check == ("local", "weak_conf")
