"""Hand-checked GraphRAG/KG chunk-config alignment tests (§11.2).

Every case fixes both configs by hand and checks the reported alignment against a
manually computed expectation:

    {size:300, overlap:50} vs {size:300, overlap:50}  -> aligned, no mismatches
    size 300 vs 310, tolerance 0                       -> size_match False
    size 300 vs 310, tolerance 10                       -> aligned (|diff|<=10)
    overlap 50 vs 60 (size equal)                       -> overlap-only mismatch
    size 300/320 + overlap 50/60                        -> both mismatch
    overlap key missing on one side                     -> mismatch, no crash
"""

from __future__ import annotations

from kg_retrievers.graphrag_chunk_alignment import ChunkAlignment, check_alignment


def test_exact_match_is_aligned() -> None:
    res = check_alignment({"size": 300, "overlap": 50}, {"size": 300, "overlap": 50})
    assert res.aligned is True
    assert res.size_match is True
    assert res.overlap_match is True
    assert res.mismatches == ()


def test_size_diff_with_zero_tolerance_flags_size() -> None:
    res = check_alignment({"size": 310, "overlap": 50}, {"size": 300, "overlap": 50})
    assert res.size_match is False
    assert res.overlap_match is True
    assert res.aligned is False
    assert "size" in res.mismatches
    assert res.mismatches == ("size",)


def test_tolerance_absorbs_the_same_size_diff() -> None:
    res = check_alignment(
        {"size": 310, "overlap": 50},
        {"size": 300, "overlap": 50},
        tolerance=10,
    )
    assert res.size_match is True
    assert res.aligned is True
    assert res.mismatches == ()


def test_overlap_only_mismatch() -> None:
    res = check_alignment({"size": 300, "overlap": 60}, {"size": 300, "overlap": 50})
    assert res.aligned is False
    assert res.size_match is True
    assert res.overlap_match is False
    assert res.mismatches == ("overlap",)


def test_both_fields_mismatch() -> None:
    res = check_alignment({"size": 320, "overlap": 60}, {"size": 300, "overlap": 50})
    assert res.aligned is False
    assert len(res.mismatches) == 2
    assert set(res.mismatches) == {"size", "overlap"}
    # fixed field order: size before overlap
    assert res.mismatches == ("size", "overlap")


def test_missing_overlap_key_is_a_mismatch_not_a_crash() -> None:
    res = check_alignment({"size": 300}, {"size": 300, "overlap": 50})
    assert res.size_match is True
    assert res.overlap_match is False
    assert res.aligned is False
    assert res.mismatches == ("overlap",)


def test_tolerance_boundary_is_inclusive() -> None:
    # |diff| == tolerance must count as a match.
    res = check_alignment(
        {"size": 305, "overlap": 55},
        {"size": 300, "overlap": 50},
        tolerance=5,
    )
    assert res.aligned is True
    assert res.mismatches == ()


def test_as_dict_shape_and_bool_type() -> None:
    res = check_alignment({"size": 300, "overlap": 50}, {"size": 300, "overlap": 50})
    d = res.as_dict()
    assert isinstance(d["aligned"], bool)
    assert d["aligned"] is True
    assert d["mismatches"] == []
    assert set(d) == {"aligned", "size_match", "overlap_match", "mismatches"}


def test_result_is_frozen() -> None:
    res = check_alignment({"size": 300, "overlap": 50}, {"size": 300, "overlap": 50})
    assert isinstance(res, ChunkAlignment)
    try:
        res.aligned = False  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ChunkAlignment must be frozen")
