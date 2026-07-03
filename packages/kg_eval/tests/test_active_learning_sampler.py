"""Tests for the active-learning annotation sampler (§23.26)."""

from __future__ import annotations

import math

from kg_eval.active_learning_sampler import SampleBatch, select, uncertainty


def test_uncertainty_peaks_at_half() -> None:
    # confidence 0.5 -> maximal uncertainty; 1.0 (and 0.0) -> none.
    assert uncertainty(0.5) == 1.0
    assert uncertainty(1.0) == 0.0
    assert uncertainty(0.0) == 0.0
    # Symmetric around 0.5 and monotone toward the middle.
    assert math.isclose(uncertainty(0.75), 0.5)
    assert math.isclose(uncertainty(0.25), 0.5)


def test_labeled_items_excluded_and_counted() -> None:
    items = [
        {"id": "a", "confidence": 0.5, "labeled": True},
        {"id": "b", "confidence": 0.5},
        {"id": "c", "confidence": 0.9, "labeled": 1},
        {"id": "d", "confidence": 0.9},
    ]
    batch = select(items, k=10)
    assert batch.skipped_labeled == 2
    assert set(batch.selected_ids) == {"b", "d"}


def test_top_k_picks_nearest_half() -> None:
    # Uncertainty order: 0.5 (1.0) > 0.6 (0.8) > 0.8 (0.4) > 0.95 (0.1).
    items = [
        {"id": "far", "confidence": 0.95},
        {"id": "mid", "confidence": 0.8},
        {"id": "near", "confidence": 0.6},
        {"id": "peak", "confidence": 0.5},
    ]
    batch = select(items, k=2)
    assert batch.selected_ids == ("peak", "near")


def test_tie_broken_by_ascending_id() -> None:
    # Both confidences give uncertainty 1.0; id asc must decide order.
    items = [
        {"id": "z", "confidence": 0.5},
        {"id": "a", "confidence": 0.5},
        {"id": "m", "confidence": 0.5},
    ]
    batch = select(items, k=2)
    assert batch.selected_ids == ("a", "m")


def test_max_per_type_caps_dominant_type() -> None:
    # The two most-uncertain items share type "rel"; cap 1 forces "ent" in.
    items = [
        {"id": "r1", "confidence": 0.5, "type": "rel"},
        {"id": "r2", "confidence": 0.52, "type": "rel"},
        {"id": "e1", "confidence": 0.7, "type": "ent"},
    ]
    batch = select(items, k=2, max_per_type=1)
    assert batch.selected_ids == ("r1", "e1")
    assert batch.per_type == {"rel": 1, "ent": 1}


def test_per_type_counts_sum_to_selected() -> None:
    items = [
        {"id": "a", "confidence": 0.5, "type": "x"},
        {"id": "b", "confidence": 0.55, "type": "y"},
        {"id": "c", "confidence": 0.6, "type": "x"},
        {"id": "d", "confidence": 0.9, "type": "y"},
    ]
    batch = select(items, k=3)
    assert sum(batch.per_type.values()) == len(batch.selected_ids) == 3


def test_as_dict_selected_ids_is_list() -> None:
    batch = SampleBatch(selected_ids=("a", "b"), skipped_labeled=1, per_type={"t": 2})
    d = batch.as_dict()
    assert isinstance(d["selected_ids"], list)
    assert d["selected_ids"] == ["a", "b"]
    assert d["skipped_labeled"] == 1
    assert d["per_type"] == {"t": 2}


def test_default_type_bucket_used() -> None:
    # Items with no explicit type share the "_" bucket.
    items = [
        {"id": "a", "confidence": 0.5},
        {"id": "b", "confidence": 0.51},
    ]
    batch = select(items, k=2, max_per_type=1)
    # max_per_type caps the shared default bucket at 1.
    assert batch.selected_ids == ("a",)
    assert batch.per_type == {"_": 1}
