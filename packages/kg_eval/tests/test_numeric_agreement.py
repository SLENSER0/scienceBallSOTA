"""Tests for Bland-Altman numeric agreement (§18.10)."""

from __future__ import annotations

import pytest

from kg_eval.numeric_agreement import AgreementReport, bland_altman


def test_perfect_agreement_is_all_zero() -> None:
    """pred == gold -> нулевые bias/sd/границы/MAE. / Identical vectors: all zero."""
    report = bland_altman([10.0, 20.0, 30.0], [10.0, 20.0, 30.0])
    assert report.bias == 0.0
    assert report.sd_diff == 0.0
    assert report.loa_lower == 0.0
    assert report.loa_upper == 0.0
    assert report.mae == 0.0


def test_constant_offset_bias_and_mae() -> None:
    """Постоянное смещение +1 -> bias==1, sd==0, mae==1. / Constant +1 offset."""
    report = bland_altman([11.0, 21.0, 31.0], [10.0, 20.0, 30.0])
    assert report.bias == 1.0
    assert report.sd_diff == 0.0
    assert report.mae == 1.0


def test_within_tolerance_all_pass() -> None:
    """tolerance=1.0 покрывает разность 1 -> доля==1.0. / tol covers diff of 1."""
    report = bland_altman([11.0, 21.0, 31.0], [10.0, 20.0, 30.0], tolerance=1.0)
    assert report.within_tol_fraction == 1.0


def test_within_tolerance_all_fail() -> None:
    """tolerance=0.5 < разность 1 -> доля==0.0. / tol below diff of 1: none pass."""
    report = bland_altman([11.0, 21.0, 31.0], [10.0, 20.0, 30.0], tolerance=0.5)
    assert report.within_tol_fraction == 0.0


def test_loa_upper_equals_bias_plus_z_sd() -> None:
    """loa_upper точно == bias + 1.96·sd_diff. / Upper LoA identity holds exactly."""
    pred = [10.0, 22.0, 33.0, 39.0]
    gold = [10.0, 20.0, 30.0, 40.0]
    report = bland_altman(pred, gold)
    assert report.loa_upper == report.bias + 1.96 * report.sd_diff
    assert report.loa_lower == report.bias - 1.96 * report.sd_diff


def test_length_mismatch_raises() -> None:
    """Разная длина -> ValueError. / Mismatched lengths raise ValueError."""
    with pytest.raises(ValueError):
        bland_altman([1.0, 2.0], [1.0])


def test_empty_raises() -> None:
    """Пустые входы -> ValueError. / Empty inputs raise ValueError."""
    with pytest.raises(ValueError):
        bland_altman([], [])


def test_as_dict_roundtrip() -> None:
    """as_dict() отдаёт n и ключевые поля. / as_dict() exposes n and fields."""
    report = bland_altman([11.0, 21.0, 31.0], [10.0, 20.0, 30.0])
    data = report.as_dict()
    assert data["n"] == 3
    assert data["bias"] == 1.0
    assert set(data) == {
        "n",
        "bias",
        "sd_diff",
        "loa_lower",
        "loa_upper",
        "mae",
        "within_tol_fraction",
    }


def test_report_is_frozen() -> None:
    """Отчёт неизменяем. / Report dataclass is frozen."""
    report = bland_altman([1.0], [1.0])
    assert isinstance(report, AgreementReport)
    with pytest.raises(AttributeError):
        report.bias = 5.0  # type: ignore[misc]
