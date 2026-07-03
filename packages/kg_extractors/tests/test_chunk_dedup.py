"""Tests for chunk de-duplication (§5.9).

Hand-checkable assertions over :func:`normalize_chunk_text`, :func:`dedup_chunks`
and :class:`DedupResult`.
"""

from __future__ import annotations

from kg_extractors.chunk_dedup import (
    DedupResult,
    dedup_chunks,
    normalize_chunk_text,
)


def _chunk(chunk_id: str, text: str) -> dict:
    return {"chunk_id": chunk_id, "text": text}


def test_normalize_collapse_and_strip():
    # Whitespace collapses, trailing punctuation noise stripped, lowercased.
    assert normalize_chunk_text("  Al   Cu.  ") == "al cu"


def test_normalize_table_variants_match():
    # 'Table 1.' and 'table 1' converge on the same key.
    assert normalize_chunk_text("Table 1.") == normalize_chunk_text("table 1")
    assert normalize_chunk_text("Table 1.") == "table 1"


def test_normalize_interior_punctuation_preserved():
    # Only leading/trailing noise is stripped; interior punctuation survives.
    assert normalize_chunk_text("Fe-Ni, alloy") == "fe-ni, alloy"


def test_normalize_all_punctuation_is_empty():
    assert normalize_chunk_text("   ...   ") == ""
    assert normalize_chunk_text("") == ""


def test_two_equal_chunks_one_group():
    result = dedup_chunks([_chunk("a", "Table 1."), _chunk("b", "table 1")])
    # First id kept, second dropped, single 2-member group.
    assert result.kept == ("a",)
    assert result.dropped == ("b",)
    assert result.groups == (("a", "b"),)


def test_three_distinct_chunks_all_singletons():
    result = dedup_chunks([_chunk("a", "alpha"), _chunk("b", "beta"), _chunk("c", "gamma")])
    assert len(result.kept) == 3
    assert result.dropped == ()
    assert result.groups == (("a",), ("b",), ("c",))


def test_earlier_chunk_id_kept_for_later_duplicate():
    # A chunk equal to a LATER one keeps the earlier chunk_id.
    result = dedup_chunks(
        [
            _chunk("first", "same text"),
            _chunk("middle", "other"),
            _chunk("last", "SAME  TEXT."),
        ]
    )
    assert result.kept == ("first", "middle")
    assert result.dropped == ("last",)
    assert result.groups == (("first", "last"), ("middle",))


def test_order_preserved_first_occurrence_kept():
    result = dedup_chunks(
        [
            _chunk("x1", "dup"),
            _chunk("x2", "dup"),
            _chunk("x3", "dup"),
        ]
    )
    assert result.kept == ("x1",)
    assert result.dropped == ("x2", "x3")
    assert result.groups == (("x1", "x2", "x3"),)


def test_empty_input():
    result = dedup_chunks([])
    assert result.kept == ()
    assert result.dropped == ()
    assert result.groups == ()


def test_dropped_is_inputs_minus_kept():
    chunks = [
        _chunk("a", "one"),
        _chunk("b", "two"),
        _chunk("c", "one"),
        _chunk("d", "three"),
        _chunk("e", "two"),
    ]
    result = dedup_chunks(chunks)
    all_ids = {c["chunk_id"] for c in chunks}
    kept_set = set(result.kept)
    assert set(result.dropped) == all_ids - kept_set
    # No id both kept and dropped.
    assert kept_set.isdisjoint(set(result.dropped))
    # Union covers every input id exactly once.
    assert kept_set | set(result.dropped) == all_ids
    assert len(result.kept) + len(result.dropped) == len(chunks)


def test_distinct_texts_never_merge():
    result = dedup_chunks([_chunk("a", "Fe-Ni"), _chunk("b", "Fe Ni")])
    # Interior punctuation keeps these apart.
    assert result.kept == ("a", "b")
    assert result.dropped == ()


def test_as_dict_groups_is_list_of_lists():
    result = dedup_chunks([_chunk("a", "Table 1."), _chunk("b", "table 1"), _chunk("c", "x")])
    data = result.as_dict()
    assert isinstance(data["groups"], list)
    assert all(isinstance(group, list) for group in data["groups"])
    assert data["groups"] == [["a", "b"], ["c"]]
    assert data["kept"] == ["a", "c"]
    assert data["dropped"] == ["b"]


def test_dataclass_is_frozen():
    result = DedupResult(kept=("a",), dropped=(), groups=(("a",),))
    try:
        result.kept = ("b",)  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("DedupResult must be frozen")
