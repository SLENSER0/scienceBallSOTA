"""Tests for the answer-unit accuracy metric — точность единиц (§18.8)."""

from __future__ import annotations

from kg_eval.unit_accuracy import UnitJudgement, judge_unit, unit_accuracy


def test_exact_and_compatible_when_identical() -> None:
    """Identical units are both exact and compatible, never mixed (§18.8)."""
    j = judge_unit("MPa", "MPa")
    assert j.exact is True
    assert j.compatible is True
    assert j.mixed is False


def test_same_dimension_is_compatible_not_exact() -> None:
    """MPa vs GPa: same dimension → compatible, not exact, not mixed (§18.8)."""
    j = judge_unit("MPa", "GPa")
    assert j.exact is False
    assert j.compatible is True
    assert j.mixed is False


def test_cross_dimension_is_mixed() -> None:
    """MPa vs K crosses dimensions → not compatible, mixed (§18.8)."""
    j = judge_unit("MPa", "K")
    assert j.compatible is False
    assert j.mixed is True


def test_missing_actual_is_all_false() -> None:
    """A None actual is neither exact, compatible, nor mixed (§18.8)."""
    j = judge_unit("MPa", None)
    assert j.exact is False
    assert j.compatible is False
    assert j.mixed is False


def test_unit_accuracy_aggregates_four_pairs() -> None:
    """Aggregate the four hand-checked pairs into expected rates (§18.8)."""
    pairs: list[tuple[str, str | None]] = [
        ("MPa", "MPa"),  # exact + compatible
        ("MPa", "GPa"),  # compatible only
        ("MPa", "K"),  # mixed
        ("MPa", None),  # nothing
    ]
    result = unit_accuracy(pairs)
    assert result["exact_rate"] == 0.25
    assert result["compatible_rate"] == 0.5
    assert result["mixed_rate"] == 0.25
    assert result["n"] == 4


def test_unit_accuracy_empty_is_all_zero() -> None:
    """An empty list yields all-zero rates and n == 0 (§18.8)."""
    result = unit_accuracy([])
    assert result["exact_rate"] == 0.0
    assert result["compatible_rate"] == 0.0
    assert result["mixed_rate"] == 0.0
    assert result["n"] == 0


def test_as_dict_keys_are_stable() -> None:
    """as_dict exposes a fixed key set for serialization (§18.8)."""
    j = judge_unit("MPa", "GPa")
    assert isinstance(j, UnitJudgement)
    assert set(j.as_dict()) == {"expected", "actual", "exact", "compatible", "mixed"}
    assert j.as_dict()["expected"] == "MPa"
    assert j.as_dict()["actual"] == "GPa"
