"""Tests for TEDS-lite table-structure similarity (§23.34/§23.31).

Hand-checkable: every fixture is a tiny table whose expected score is computed
by hand in the assertion, no golden files.
"""

from __future__ import annotations

from kg_eval.table_teds import TableScore, grid_align, normalize_cell


def test_normalize_cell_strip_collapse_casefold() -> None:
    """' Fe  0.5 ' folds to 'fe 0.5' (§23.34)."""
    assert normalize_cell(" Fe  0.5 ") == "fe 0.5"
    assert normalize_cell("MPa") == "mpa"
    assert normalize_cell("\tA\n\tB\t") == "a b"


def test_identical_2x2_perfect() -> None:
    """Identical 2x2: structure 1.0, content 1.0, shape_match True (§23.34)."""
    t = [["a", "b"], ["c", "d"]]
    score = grid_align(t, [row[:] for row in t])
    assert score.structure_similarity == 1.0
    assert score.content_accuracy == 1.0
    assert score.shape_match is True
    assert score.n_gold_cells == 4
    assert score.n_pred_cells == 4
    assert score.cell_content_matches == 4


def test_shape_mismatch_2x2_vs_2x3() -> None:
    """A 2x2 vs 2x3 prediction has shape_match False (§23.34)."""
    gold = [["a", "b"], ["c", "d"]]
    pred = [["a", "b", "x"], ["c", "d", "y"]]
    score = grid_align(gold, pred)
    assert score.shape_match is False
    assert score.n_gold_cells == 4
    assert score.n_pred_cells == 6
    # 4 aligned positions all match content, but structure penalised for 2 extra.
    assert score.cell_content_matches == 4
    assert score.structure_similarity == 4 / 6
    assert score.content_accuracy == 1.0


def test_one_differing_cell_2x2() -> None:
    """One differing cell in a 2x2 gives content_accuracy 0.75 (§23.34)."""
    gold = [["a", "b"], ["c", "d"]]
    pred = [["a", "b"], ["c", "X"]]
    score = grid_align(gold, pred)
    assert score.content_accuracy == 0.75
    assert score.structure_similarity == 1.0
    assert score.shape_match is True
    assert score.cell_content_matches == 3


def test_empty_gold_and_empty_pred() -> None:
    """Empty gold and empty pred: structure 1.0, content 0.0 (§23.34)."""
    score = grid_align([], [])
    assert score.structure_similarity == 1.0
    assert score.content_accuracy == 0.0
    assert score.n_gold_cells == 0
    assert score.n_pred_cells == 0
    assert score.shape_match is True


def test_empty_gold_nonempty_pred_content_zero() -> None:
    """Empty gold scores content_accuracy 0.0 regardless of pred (§23.34)."""
    score = grid_align([], [["a"]])
    assert score.content_accuracy == 0.0
    assert score.structure_similarity == 0.0  # 0 matched / max(0, 1)


def test_fully_mismatched_content_1x2_keeps_structure() -> None:
    """1x2 with all content wrong: structure 1.0, content 0.0 (§23.34)."""
    gold = [["a", "b"]]
    pred = [["x", "y"]]
    score = grid_align(gold, pred)
    assert score.structure_similarity == 1.0
    assert score.content_accuracy == 0.0
    assert score.shape_match is True
    assert score.cell_content_matches == 0


def test_casefold_and_whitespace_count_as_match() -> None:
    """Cells matching only after normalization still count (§23.34)."""
    gold = [["Fe 0.5", "B"]]
    pred = [[" fe  0.5 ", "b"]]
    score = grid_align(gold, pred)
    assert score.content_accuracy == 1.0
    assert score.cell_content_matches == 2


def test_as_dict_stable_keys() -> None:
    """as_dict() exposes the six frozen fields (§23.34)."""
    score = grid_align([["a"]], [["a"]])
    d = score.as_dict()
    assert d == {
        "n_gold_cells": 1,
        "n_pred_cells": 1,
        "shape_match": True,
        "cell_content_matches": 1,
        "structure_similarity": 1.0,
        "content_accuracy": 1.0,
    }
    assert isinstance(score, TableScore)


def test_ragged_rows_align_per_axis() -> None:
    """Ragged rows align per-axis up to min shape (§23.34)."""
    gold = [["a", "b"], ["c"]]
    pred = [["a", "b", "z"], ["c", "d"]]
    score = grid_align(gold, pred)
    assert score.n_gold_cells == 3
    assert score.n_pred_cells == 5
    # Aligned positions: (0,0),(0,1),(1,0) -> all match content.
    assert score.cell_content_matches == 3
    assert score.content_accuracy == 1.0
    assert score.structure_similarity == 3 / 5
    assert score.shape_match is False
