"""Tests for coverage inequality / concentration metrics (§25.5).

Hand-checkable assertions on the Gini coefficient and on the per-material /
per-property aggregation. Тесты неравенства покрытия.
"""

from __future__ import annotations

from kg_retrievers.coverage_inequality import (
    CoverageInequality,
    coverage_inequality,
    gini,
)


def test_gini_uniform_is_zero() -> None:
    """A perfectly equal vector has zero inequality (§25.5)."""
    assert gini([1, 1, 1, 1]) == 0.0


def test_gini_extreme_concentration_exact() -> None:
    """gini([0, 0, 0, 10]) == 0.75 exactly (§25.5).

    Sorted [0,0,0,10], n=4, Σx=10: (2·(4·10))/(4·10) - 5/4 = 2 - 1.25 = 0.75.
    """
    assert gini([0, 0, 0, 10]) == 0.75


def test_gini_degenerate_vectors() -> None:
    """Empty and single-element vectors return 0.0 (§25.5)."""
    assert gini([]) == 0.0
    assert gini([5]) == 0.0


def test_gini_all_zero_is_zero() -> None:
    """An all-zero vector has zero inequality (guarded division) (§25.5)."""
    assert gini([0, 0, 0]) == 0.0


def test_gini_mixed_vector_in_unit_interval() -> None:
    """A mixed non-negative vector yields a Gini in [0.0, 1.0] (§25.5)."""
    value = gini([1, 2, 3, 4, 5, 40])
    assert 0.0 <= value <= 1.0


def test_most_and_least_covered_material() -> None:
    """Materials {A:0, B:10}: most=='B', least=='A' (§25.5)."""
    cells = [
        {"material": "A", "property": "band_gap", "evidence_count": 0},
        {"material": "B", "property": "band_gap", "evidence_count": 10},
    ]
    result = coverage_inequality(cells)
    assert result.most_covered_material == "B"
    assert result.least_covered_material == "A"


def test_distinct_key_counts() -> None:
    """n_materials / n_properties count distinct keys, not cells (§25.5)."""
    cells = [
        {"material": "A", "property": "p1", "evidence_count": 1},
        {"material": "A", "property": "p2", "evidence_count": 2},
        {"material": "B", "property": "p1", "evidence_count": 3},
    ]
    result = coverage_inequality(cells)
    assert result.n_materials == 2
    assert result.n_properties == 2


def test_evidence_aggregates_per_key() -> None:
    """Evidence sums across cells sharing a material/property (§25.5)."""
    cells = [
        {"material": "A", "property": "p1", "evidence_count": 4},
        {"material": "A", "property": "p1", "evidence_count": 6},
        {"material": "B", "property": "p1", "evidence_count": 0},
    ]
    result = coverage_inequality(cells)
    # Per-material totals {A:10, B:0} → same shape as gini([0, 10]).
    assert result.gini_material == gini([0, 10])
    assert result.most_covered_material == "A"
    assert result.least_covered_material == "B"


def test_as_dict_exposes_all_six_fields() -> None:
    """as_dict() surfaces all six dataclass fields (§25.5)."""
    result = coverage_inequality([{"material": "A", "property": "p1", "evidence_count": 5}])
    data = result.as_dict()
    assert set(data) == {
        "gini_material",
        "gini_property",
        "n_materials",
        "n_properties",
        "most_covered_material",
        "least_covered_material",
    }
    assert data["n_materials"] == 1
    assert data["most_covered_material"] == "A"


def test_empty_input_has_none_extremes() -> None:
    """No cells → zero counts, None extremes, zero Gini (§25.5)."""
    result = coverage_inequality([])
    assert result == CoverageInequality(
        gini_material=0.0,
        gini_property=0.0,
        n_materials=0,
        n_properties=0,
        most_covered_material=None,
        least_covered_material=None,
    )
