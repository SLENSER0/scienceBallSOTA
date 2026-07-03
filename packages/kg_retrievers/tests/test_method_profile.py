"""Tests for the §24.11 per-method profile card builder.

Тесты сборщика карточки метода из §24.11.
"""

from __future__ import annotations

from kg_retrievers.method_profile import (
    MethodProfile,
    build_method_profile,
    confidence_from_sources,
)


def test_five_distinct_sources_high() -> None:
    """(1) 5 distinct source ids → 'high' band and source_count == 5."""
    record = {"method_id": "m1", "principle": "diffusion"}
    profile = build_method_profile(record, ["a", "b", "c", "d", "e"])
    assert profile.source_count == 5
    assert profile.confidence == "high"


def test_duplicate_sources_deduped_before_counting() -> None:
    """(2) Duplicate source ids collapse to one before counting → 'low'."""
    profile = build_method_profile({"method_id": "m2"}, ["a", "a"])
    assert profile.source_count == 1
    assert profile.confidence == "low"


def test_zero_sources_none() -> None:
    """(3) No supporting sources → 'none' band."""
    profile = build_method_profile({"method_id": "m3"}, [])
    assert profile.source_count == 0
    assert profile.confidence == "none"


def test_tuple_fields_dedupe_preserve_first_seen_order() -> None:
    """(4) Tuple fields dedupe while preserving first-seen order."""
    record = {
        "method_id": "m4",
        "performance_metrics": ["auc", "f1", "auc", "recall", "f1"],
    }
    profile = build_method_profile(record, ["s"])
    assert profile.performance_metrics == ("auc", "f1", "recall")


def test_missing_capex_is_none() -> None:
    """(5) A missing 'capex' key yields capex is None."""
    profile = build_method_profile({"method_id": "m5"}, ["s"])
    assert profile.capex is None
    assert profile.opex is None


def test_as_dict_performance_metrics_is_list() -> None:
    """(6) as_dict() renders performance_metrics as a list."""
    record = {"method_id": "m6", "performance_metrics": ["auc", "f1"]}
    profile = build_method_profile(record, ["s"])
    dumped = profile.as_dict()
    assert isinstance(dumped["performance_metrics"], list)
    assert dumped["performance_metrics"] == ["auc", "f1"]


def test_confidence_from_sources_three_is_medium() -> None:
    """(7) confidence_from_sources(3) == 'medium'."""
    assert confidence_from_sources(3) == "medium"


def test_confidence_band_boundaries() -> None:
    """Full band table incl. negative guard and the medium/high boundary."""
    assert confidence_from_sources(-1) == "none"
    assert confidence_from_sources(0) == "none"
    assert confidence_from_sources(1) == "low"
    assert confidence_from_sources(2) == "medium"
    assert confidence_from_sources(4) == "high"


def test_frozen_profile_is_immutable() -> None:
    """The dataclass is frozen — attribute assignment must raise."""
    import dataclasses

    profile = build_method_profile({"method_id": "m7"}, [])
    assert isinstance(profile, MethodProfile)
    try:
        profile.confidence = "high"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guards against a non-frozen regression
        raise AssertionError("MethodProfile must be frozen")


def test_scalar_fields_coerced_to_str() -> None:
    """Non-string scalars are coerced; input conditions dedupe too."""
    record = {
        "method_id": 42,
        "principle": 7,
        "input_conditions": ["x", "x", "y"],
    }
    profile = build_method_profile(record, ["s1", "s2", "s3"])
    assert profile.method_id == "42"
    assert profile.principle == "7"
    assert profile.input_conditions == ("x", "y")
    assert profile.confidence == "medium"
