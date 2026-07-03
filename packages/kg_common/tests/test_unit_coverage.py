"""Unit-coverage report over a measurement population (§7.12)."""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.units.coverage import UnitCoverage, unit_coverage


@dataclass(frozen=True)
class _Meas:
    """Attribute-bearing measurement (объект, not a dict) for robustness tests."""

    unit: str | None


def test_with_and_without_unit_counts() -> None:
    # 3 carry a unit, 2 do not → total 5, with_unit 3, without_unit 2.
    pop = [
        {"unit": "HV"},
        {"unit": "MPa"},
        {"unit": "HV"},
        {"unit": None},
        {"unit": ""},
    ]
    cov = unit_coverage(pop)
    assert cov.total == 5
    assert cov.with_unit == 3
    assert cov.without_unit == 2
    # invariant: total splits exactly into with/without.
    assert cov.total == cov.with_unit + cov.without_unit


def test_by_unit_histogram_exact() -> None:
    # HV ×3, MPa ×1 among the four unit-bearing measurements; None is skipped.
    pop = [{"unit": "HV"}, {"unit": "MPa"}, {"unit": "HV"}, {"unit": "HV"}, {"unit": None}]
    cov = unit_coverage(pop)
    assert cov.by_unit == {"HV": 3, "MPa": 1}
    # histogram covers exactly the unit-bearing measurements.
    assert sum(cov.by_unit.values()) == cov.with_unit == 4
    # ordered by descending count → HV before MPa.
    assert list(cov.by_unit) == ["HV", "MPa"]


def test_missing_unit_ratio_exact() -> None:
    # 2 of 5 lack a unit → 0.4 exactly.
    pop = [{"unit": "V"}, {"unit": "V"}, {"unit": "V"}, {}, {"unit": "   "}]
    cov = unit_coverage(pop)
    assert cov.without_unit == 2
    assert cov.missing_unit_ratio == 0.4


def test_all_with_unit_ratio_is_zero() -> None:
    # Every measurement carries a unit → missing ratio 0.0, without_unit 0.
    pop = [{"unit": "HV"}, {"unit": "MPa"}, {"unit": "mg/L"}]
    cov = unit_coverage(pop)
    assert cov.without_unit == 0
    assert cov.missing_unit_ratio == 0.0
    assert cov.with_unit == cov.total == 3


def test_empty_population_is_zeros() -> None:
    cov = unit_coverage([])
    assert cov.total == 0
    assert cov.with_unit == 0
    assert cov.without_unit == 0
    assert cov.by_unit == {}
    # empty population must not divide by zero → ratio pinned to 0.0.
    assert cov.missing_unit_ratio == 0.0


def test_as_dict_shape_and_values() -> None:
    pop = [{"unit": "HV"}, {"unit": "HV"}, {"unit": None}]
    cov = unit_coverage(pop)
    d = cov.as_dict()
    assert isinstance(cov, UnitCoverage)
    assert set(d) == {"total", "with_unit", "without_unit", "by_unit", "missing_unit_ratio"}
    assert d["total"] == 3
    assert d["with_unit"] == 2
    assert d["without_unit"] == 1
    assert d["by_unit"] == {"HV": 2}
    assert d["missing_unit_ratio"] == 1 / 3
    # as_dict copies the histogram — mutating the copy must not touch the report.
    d["by_unit"]["HV"] = 999
    assert cov.by_unit == {"HV": 2}


def test_missing_unit_ratio_in_unit_interval() -> None:
    populations = [
        [],
        [{"unit": "HV"}],
        [{"unit": None}],
        [{"unit": "HV"}, {"unit": None}, {}, {"unit": "MPa"}],
        [{} for _ in range(7)],
    ]
    for pop in populations:
        cov = unit_coverage(pop)
        assert 0.0 <= cov.missing_unit_ratio <= 1.0


def test_all_missing_ratio_is_one() -> None:
    # None + missing key + blank string → every measurement missing → ratio 1.0.
    pop = [{"unit": None}, {}, {"unit": "  "}]
    cov = unit_coverage(pop)
    assert cov.with_unit == 0
    assert cov.by_unit == {}
    assert cov.missing_unit_ratio == 1.0


def test_objects_and_stripping() -> None:
    # Attribute-bearing objects work like dicts; units are stripped, blanks drop.
    pop = [_Meas(unit="HV"), _Meas(unit="  MPa  "), _Meas(unit=None), _Meas(unit="")]
    cov = unit_coverage(pop)
    assert cov.total == 4
    assert cov.with_unit == 2
    assert cov.by_unit == {"HV": 1, "MPa": 1}  # "  MPa  " stripped to "MPa"


def test_accepts_generator_input() -> None:
    # Population may be any one-shot iterable, not just a list.
    cov = unit_coverage({"unit": u} for u in ("HV", "HV", "MPa", None))
    assert cov.total == 4
    assert cov.by_unit == {"HV": 2, "MPa": 1}
    assert cov.without_unit == 1
