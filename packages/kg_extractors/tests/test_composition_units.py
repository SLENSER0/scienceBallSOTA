"""Tests for §7.2 composition unit interconversion (wt% ↔ at% ↔ ppm ↔ ppb).

Hand-checkable: Fe=55.845, Ni=58.6934, C=12.011 g/mol. For an equimass Fe/Ni
alloy, moles ∝ 50/M: Fe→0.8953, Ni→0.8520, so Fe at% = 51.24; symmetrically the
at→wt inverse gives Fe wt% = 48.76. ppm/ppb scalings are exact decade shifts.
"""

from __future__ import annotations

import pytest

from kg_extractors.materials.composition_units import (
    CompositionConversion,
    at_to_wt,
    ppm_to_ppb,
    ppm_to_wt_percent,
    wt_percent_to_ppm,
    wt_to_at,
)


def test_wt_to_at_fe_ni() -> None:
    assert wt_to_at({"Fe": 50, "Ni": 50})["Fe"] == pytest.approx(51.24, abs=0.05)


def test_at_to_wt_fe_ni() -> None:
    assert at_to_wt({"Fe": 50, "Ni": 50})["Fe"] == pytest.approx(48.76, abs=0.05)


def test_round_trip_fe_c() -> None:
    assert at_to_wt(wt_to_at({"Fe": 70, "C": 30}))["Fe"] == pytest.approx(70, abs=0.1)


def test_wt_percent_to_ppm() -> None:
    assert wt_percent_to_ppm(0.5) == 5000.0


def test_ppm_to_wt_percent() -> None:
    assert ppm_to_wt_percent(10000) == 1.0


def test_ppm_to_ppb() -> None:
    assert ppm_to_ppb(1) == 1000.0


def test_wt_to_at_sums_to_100() -> None:
    assert sum(wt_to_at({"Fe": 50, "Ni": 50}).values()) == pytest.approx(100, abs=1e-6)


def test_wt_to_at_len() -> None:
    assert wt_to_at({"Fe": 50, "Ni": 50}).__len__() == 2


def test_conversion_method_tag() -> None:
    result = wt_to_at({"Fe": 50, "Ni": 50})
    conv = CompositionConversion(
        basis="at",
        fractions=tuple(result.items()),
        method="converted",
    )
    assert conv.as_dict()["method"] == "converted"


def test_conversion_as_dict_shape() -> None:
    conv = CompositionConversion(
        basis="at",
        fractions=(("Fe", 51.24), ("Ni", 48.76)),
        method="converted",
    )
    d = conv.as_dict()
    assert d["basis"] == "at"
    assert d["fractions"] == [["Fe", 51.24], ["Ni", 48.76]]
