"""Tests for ``normalization_method`` classification (§7.5)."""

from __future__ import annotations

from kg_common.units.normalization_method import (
    METHODS,
    MethodDecision,
    classify_normalization_method,
)


def test_direct_same_unit() -> None:
    """Identical raw/canonical units → ``direct``."""
    d = classify_normalization_method("HV", "HV")
    assert d.method == "direct"
    assert d.canonical_unit == "HV"


def test_direct_case_insensitive() -> None:
    """Case-folded match still counts as ``direct``."""
    assert classify_normalization_method("hv", "HV").method == "direct"


def test_converted_differing_units() -> None:
    """Two distinct real units → ``converted``, canonical preserved."""
    d = classify_normalization_method("ksi", "MPa")
    assert d.method == "converted"
    assert d.canonical_unit == "MPa"


def test_rule_when_rule_based() -> None:
    """``rule_based`` conversion outranks a unit mismatch → ``rule``."""
    assert classify_normalization_method("HRC", "HV", rule_based=True).method == "rule"


def test_manual_wins_first() -> None:
    """``manual`` overrides even a direct-unit match."""
    assert classify_normalization_method("MPa", "MPa", manual=True).method == "manual"


def test_rule_when_assumed_and_missing_raw() -> None:
    """Missing raw unit + ``assumed`` → ``rule``."""
    assert classify_normalization_method(None, "HV", assumed=True).method == "rule"


def test_rule_when_unit_missing_no_flags() -> None:
    """A missing unit with no flags still falls through to ``rule``."""
    assert classify_normalization_method(None, "HV").method == "rule"
    assert classify_normalization_method("HV", None).method == "rule"


def test_manual_beats_rule_based() -> None:
    """Priority: ``manual`` outranks ``rule_based``."""
    d = classify_normalization_method("HRC", "HV", manual=True, rule_based=True)
    assert d.method == "manual"


def test_all_methods_are_legal() -> None:
    """Every produced label is a member of :data:`METHODS`."""
    cases = [
        classify_normalization_method("HV", "HV"),
        classify_normalization_method("ksi", "MPa"),
        classify_normalization_method("HRC", "HV", rule_based=True),
        classify_normalization_method("MPa", "MPa", manual=True),
    ]
    for c in cases:
        assert c.method in METHODS


def test_blank_unit_treated_as_missing() -> None:
    """Whitespace-only units are treated as absent → ``rule``."""
    assert classify_normalization_method("  ", "HV").method == "rule"


def test_as_dict_roundtrip() -> None:
    """``as_dict`` exposes exactly the three fields."""
    d = classify_normalization_method("ksi", "MPa")
    assert d.as_dict() == {
        "method": "converted",
        "canonical_unit": "MPa",
        "reason": d.reason,
    }
    assert isinstance(d, MethodDecision)


def test_frozen_dataclass() -> None:
    """:class:`MethodDecision` is immutable."""
    d = classify_normalization_method("HV", "HV")
    try:
        d.method = "manual"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("MethodDecision should be frozen")
