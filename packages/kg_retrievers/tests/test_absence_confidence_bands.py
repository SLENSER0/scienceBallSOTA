"""Tests for absence-confidence bands / abstain zone (§25.11).

Ручная проверка полос уверенности: границы HIGH/MID/LOW/UNKNOWN, суммирование
долей до 1.0, зона воздержания = размер MID, усечение примеров и пустой вход.
"""

from __future__ import annotations

from kg_retrievers.absence_confidence_bands import (
    Band,
    ConfidenceBands,
    band_for,
    bucket_bands,
)


def _bands_by_name(cb: ConfidenceBands) -> dict[str, Band]:
    return {b.name: b for b in cb.bands}


# -- band_for boundaries ----------------------------------------------------
def test_conf_high() -> None:
    assert band_for(0.8, high_at=0.6, low_at=0.25) == "HIGH"


def test_conf_mid() -> None:
    assert band_for(0.4, high_at=0.6, low_at=0.25) == "MID"


def test_conf_low() -> None:
    assert band_for(0.1, high_at=0.6, low_at=0.25) == "LOW"


def test_conf_unknown_string() -> None:
    assert band_for("unknown", high_at=0.6, low_at=0.25) == "UNKNOWN"


def test_conf_none_is_unknown() -> None:
    assert band_for(None, high_at=0.6, low_at=0.25) == "UNKNOWN"


def test_conf_bool_is_unknown() -> None:
    # bool subclasses int but must not be read as a numeric confidence.
    assert band_for(True, high_at=0.6, low_at=0.25) == "UNKNOWN"


def test_band_for_edges() -> None:
    # >= high_at is HIGH; exactly low_at is MID (LOW is strict <).
    assert band_for(0.6, high_at=0.6, low_at=0.25) == "HIGH"
    assert band_for(0.25, high_at=0.6, low_at=0.25) == "MID"
    assert band_for(0.2499, high_at=0.6, low_at=0.25) == "LOW"


# -- bucket_bands aggregation ----------------------------------------------
def _cells() -> list[dict]:
    return [
        {"material_name": "GO", "property_name": "recovery", "confidence_of_absence": 0.9},
        {"material_name": "rGO", "property_name": "capex", "confidence_of_absence": 0.7},
        {"material_name": "CNT", "property_name": "opex", "confidence_of_absence": 0.4},
        {"material_name": "MXene", "property_name": "flux", "confidence_of_absence": 0.3},
        {"material_name": "Zeolite", "property_name": "cost", "confidence_of_absence": 0.1},
        {"material_name": "Alumina", "property_name": "area", "confidence_of_absence": "unknown"},
    ]


def test_shares_sum_to_one() -> None:
    cb = bucket_bands(_cells(), high_at=0.6, low_at=0.25)
    assert cb.n_total == 6
    total = sum(b.share for b in cb.bands)
    assert abs(total - 1.0) < 1e-9


def test_band_counts() -> None:
    cb = bucket_bands(_cells(), high_at=0.6, low_at=0.25)
    by = _bands_by_name(cb)
    assert by["HIGH"].count == 2  # 0.9, 0.7
    assert by["MID"].count == 2  # 0.4, 0.3
    assert by["LOW"].count == 1  # 0.1
    assert by["UNKNOWN"].count == 1  # "unknown"


def test_abstain_zone_equals_mid_count() -> None:
    cb = bucket_bands(_cells(), high_at=0.6, low_at=0.25)
    by = _bands_by_name(cb)
    assert cb.n_abstain_zone == by["MID"].count == 2


def test_examples_truncated_to_max() -> None:
    cells = [
        {"material_name": f"m{i}", "property_name": "p", "confidence_of_absence": 0.9}
        for i in range(12)
    ]
    cb = bucket_bands(cells, high_at=0.6, low_at=0.25, max_examples=5)
    by = _bands_by_name(cb)
    assert by["HIGH"].count == 12
    assert len(by["HIGH"].examples) == 5
    assert by["HIGH"].examples[0] == ("m0", "p")


def test_empty_input_no_divide_by_zero() -> None:
    cb = bucket_bands([], high_at=0.6, low_at=0.25)
    assert cb.n_total == 0
    assert cb.n_abstain_zone == 0
    assert all(b.count == 0 and b.share == 0.0 for b in cb.bands)


def test_as_dict_roundtrip() -> None:
    cb = bucket_bands(_cells(), high_at=0.6, low_at=0.25, max_examples=2)
    d = cb.as_dict()
    assert d["n_total"] == 6
    assert d["n_abstain_zone"] == 2
    names = [b["name"] for b in d["bands"]]
    assert names == ["HIGH", "MID", "LOW", "UNKNOWN"]
    # examples serialise as lists of [subject, detail] pairs.
    high = next(b for b in d["bands"] if b["name"] == "HIGH")
    assert high["examples"][0] == ["GO", "recovery"]


def test_band_as_dict() -> None:
    b = Band(name="HIGH", count=1, share=0.5, examples=[("GO", "recovery")])
    assert b.as_dict() == {
        "name": "HIGH",
        "count": 1,
        "share": 0.5,
        "examples": [["GO", "recovery"]],
    }
