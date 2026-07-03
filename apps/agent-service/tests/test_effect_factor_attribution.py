"""§13.17 tests — per-factor effect attribution («что влияет на эффект»)."""

from __future__ import annotations

import orjson
from agent_service.effect_factor_attribution import FactorBucket, attribute_effects


def _row(temp: float, effect: object, *, time_h: float = 4.0, comp: str = "A") -> dict:
    """Build one experiment row with a full ``processing`` block."""
    return {
        "processing": {"temperature_c": temp, "time_h": time_h, "composition": comp},
        "effect": effect,
    }


def test_two_buckets_by_temperature() -> None:
    """(1) temperature_c 180 (10, 20) and 200 (5) -> two distinct buckets."""
    rows = [_row(180, 10), _row(180, 20), _row(200, 5)]
    buckets = attribute_effects(rows, "temperature_c")
    assert len(buckets) == 2
    assert {b.value for b in buckets} == {180, 200}


def test_180_bucket_aggregates() -> None:
    """(2) the 180 bucket: n==2, min==10, max==20, mean==15."""
    rows = [_row(180, 10), _row(180, 20), _row(200, 5)]
    b180 = next(b for b in attribute_effects(rows, "temperature_c") if b.value == 180)
    assert b180.n == 2
    assert b180.effect_min == 10
    assert b180.effect_max == 20
    assert b180.effect_mean == 15


def test_ordered_widest_spread_first() -> None:
    """(3) the wide 180 bucket (spread 10) precedes the single-row 200 bucket."""
    rows = [_row(200, 5), _row(180, 10), _row(180, 20)]
    buckets = attribute_effects(rows, "temperature_c")
    assert [b.value for b in buckets] == [180, 200]


def test_tie_broken_by_mean() -> None:
    """Equal spread (both single-row -> spread 0) -> higher mean first."""
    rows = [_row(180, 5), _row(200, 40)]
    buckets = attribute_effects(rows, "temperature_c")
    assert [b.value for b in buckets] == [200, 180]


def test_row_missing_factor_skipped() -> None:
    """(4) a row lacking the factor is skipped and not counted."""
    rows = [
        {"processing": {"time_h": 4.0, "composition": "A"}, "effect": 99},
        _row(180, 10),
    ]
    buckets = attribute_effects(rows, "temperature_c")
    assert len(buckets) == 1
    assert buckets[0].value == 180
    assert buckets[0].n == 1


def test_non_numeric_and_bool_effect_skipped() -> None:
    """(5) rows with non-numeric or bool effect are skipped."""
    rows = [_row(180, "high"), _row(180, True), _row(180, 12)]
    buckets = attribute_effects(rows, "temperature_c")
    assert len(buckets) == 1
    assert buckets[0].n == 1
    assert buckets[0].effect_mean == 12


def test_empty_input_returns_empty() -> None:
    """(6) empty input -> []."""
    assert attribute_effects([], "temperature_c") == []


def test_single_row_bucket_min_eq_max_eq_mean() -> None:
    """(7) a single-row bucket has min == max == mean."""
    (bucket,) = attribute_effects([_row(180, 7)], "temperature_c")
    assert bucket.effect_min == bucket.effect_max == bucket.effect_mean == 7


def test_as_dict_orjson_serialisable() -> None:
    """(8) as_dict round-trips through orjson with all fields intact."""
    bucket = FactorBucket("temperature_c", 180, 2, 10.0, 20.0, 15.0)
    payload = orjson.loads(orjson.dumps(bucket.as_dict()))
    assert payload == {
        "factor": "temperature_c",
        "value": 180,
        "n": 2,
        "effect_min": 10.0,
        "effect_max": 20.0,
        "effect_mean": 15.0,
    }


def test_grouping_by_composition_factor() -> None:
    """Factor generalises to non-numeric processing keys (composition)."""
    rows = [_row(180, 10, comp="A"), _row(200, 30, comp="A"), _row(180, 5, comp="B")]
    buckets = attribute_effects(rows, "composition")
    assert [b.value for b in buckets] == ["A", "B"]
    a = buckets[0]
    assert a.n == 2 and a.effect_min == 10 and a.effect_max == 30 and a.effect_mean == 20
