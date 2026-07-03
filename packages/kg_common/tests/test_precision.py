"""Tests for significant-figure & precision tracking (§7.4/§7.5).

Hand-checkable: every expected value is worked out from the sig-fig rules
(leading zeros never count; trailing zeros count only with a decimal point).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_common.units.precision import (
    PrecisionInfo,
    describe,
    round_to_sigfigs,
    round_to_uncertainty,
    significant_figures,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.00320", 3),  # leading zeros drop, trailing zero kept (point present)
        ("1.200", 4),  # all four figures certain
        ("1500", 2),  # no point → trailing zeros not significant
        ("1.5e3", 2),  # exponent ignored, mantissa has 2 figures
        ("100.", 3),  # bare point makes trailing zeros significant
        ("42", 2),
        ("0.5", 1),
        ("007", 1),  # leading zeros drop
        ("100", 1),  # no point → single figure
        ("-3.140", 4),  # sign ignored
        ("6.02E23", 3),  # capital E exponent
        ("0.0", 1),  # pure zero
    ],
)
def test_significant_figures(raw: str, expected: int) -> None:
    assert significant_figures(raw) == expected


def test_round_to_sigfigs_examples() -> None:
    assert round_to_sigfigs(123456, 3) == 123000.0
    assert round_to_sigfigs(0.0034567, 2) == 0.0035


@pytest.mark.parametrize(
    ("value", "sig", "expected"),
    [
        (123456, 3, 123000.0),
        (0.0034567, 2, 0.0035),
        (0.0, 3, 0.0),
        (9.99, 1, 10.0),  # rounds up across the decade boundary
        (2.5, 1, 2.0),  # banker's rounding to even
        (-1234.0, 2, -1200.0),
        (1000.0, 1, 1000.0),  # power of ten, no log10 drift
    ],
)
def test_round_to_sigfigs_cases(value: float, sig: int, expected: float) -> None:
    assert round_to_sigfigs(value, sig) == expected


def test_round_to_sigfigs_returns_float() -> None:
    result = round_to_sigfigs(123456, 3)
    assert isinstance(result, float)


def test_round_to_sigfigs_rejects_zero_sig() -> None:
    with pytest.raises(ValueError):
        round_to_sigfigs(1.23, 0)


def test_round_to_uncertainty_example() -> None:
    assert round_to_uncertainty(1.827, 0.12) == (1.8, 0.1)


@pytest.mark.parametrize(
    ("value", "unc", "expected"),
    [
        (1.827, 0.12, (1.8, 0.1)),
        (12345.0, 678.0, (12300.0, 700.0)),  # unc→700 (1 sf), value to 100s
        (3.14159, 0.05, (3.14, 0.05)),
        (100.0, 0.0, (100.0, 0.0)),  # zero uncertainty: value untouched
    ],
)
def test_round_to_uncertainty_cases(
    value: float, unc: float, expected: tuple[float, float]
) -> None:
    assert round_to_uncertainty(value, unc) == expected


def test_describe_sig_figs() -> None:
    assert describe("1.200").as_dict()["sig_figs"] == 4


def test_describe_full() -> None:
    info = describe("0.00320")
    assert isinstance(info, PrecisionInfo)
    assert info.sig_figs == 3
    # 0.0032 with 3 figures → least significant digit at the 5th decimal place.
    assert info.decimals == 5
    assert info.rounded == 0.0032


def test_describe_integer_decimals_negative() -> None:
    info = describe("1500")
    # 2 figures, last certain digit is the hundreds place → decimals == -2.
    assert info.sig_figs == 2
    assert info.decimals == -2
    assert info.rounded == 1500.0


def test_describe_sig_override() -> None:
    info = describe("1.23456", sig=2)
    assert info.sig_figs == 2
    assert info.rounded == 1.2


def test_precision_info_as_dict_shape() -> None:
    info = describe("100.")
    assert info.as_dict() == {"sig_figs": 3, "decimals": 0, "rounded": 100.0}


def test_precision_info_frozen() -> None:
    info = describe("1.200")
    with pytest.raises(FrozenInstanceError):
        info.sig_figs = 9  # type: ignore[misc]


def test_significant_figures_rejects_empty() -> None:
    with pytest.raises(ValueError):
        significant_figures("   ")


def test_significant_figures_rejects_non_numeric() -> None:
    with pytest.raises(ValueError):
        significant_figures("abc")
