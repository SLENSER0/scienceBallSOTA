"""Tests for §25.14 per-cell absence-verdict rationale builder."""

from __future__ import annotations

from kg_retrievers.absence_rationale import AbsenceRationale, build_rationale


def _cell(**over: object) -> dict:
    """A well-formed absence cell with fields overridable per test."""
    base: dict = {
        "verdict": "possible_miss",
        "p_extractor_missed": 0.42,
        "has_mentions": True,
        "recall": 0.73,
        "retracted_count": 0,
        "calibrated": True,
    }
    base.update(over)
    return base


def test_possible_miss_headline() -> None:
    """verdict 'possible_miss' -> headline names 'пропуск извлечения'."""
    r = build_rationale(_cell(verdict="possible_miss"))
    assert "пропуск извлечения" in r.headline


def test_genuine_gap_headline() -> None:
    """verdict 'genuine_gap' -> headline names 'реальный пробел'."""
    r = build_rationale(_cell(verdict="genuine_gap"))
    assert "реальный пробел" in r.headline


def test_retracted_adds_factor_with_count() -> None:
    """verdict 'retracted', retracted_count 2 -> a retraction factor names '2'."""
    r = build_rationale(_cell(verdict="retracted", retracted_count=2))
    retraction_factors = [f for f in r.factors if "тзыв" in f or "retraction" in f]
    assert retraction_factors, "expected a retraction factor"
    assert any("2" in f for f in retraction_factors)


def test_no_retraction_factor_when_count_zero() -> None:
    """retracted_count 0 -> no retraction factor is emitted."""
    r = build_rationale(_cell(retracted_count=0))
    assert not any("retraction" in f or "тзыв" in f for f in r.factors)


def test_has_mentions_true_adds_mentions_factor() -> None:
    """has_mentions True -> a MENTIONS factor is present."""
    r = build_rationale(_cell(has_mentions=True))
    assert any("MENTIONS" in f for f in r.factors)


def test_has_mentions_false_omits_mentions_factor() -> None:
    """has_mentions False -> no MENTIONS factor."""
    r = build_rationale(_cell(has_mentions=False))
    assert not any("MENTIONS" in f for f in r.factors)


def test_a_factor_contains_the_recall_value() -> None:
    """The recall value (formatted) appears in some factor string."""
    r = build_rationale(_cell(recall=0.73))
    assert any("0.73" in f for f in r.factors)


def test_calibrated_flag_copied_through() -> None:
    """The calibrated flag is copied verbatim onto the dataclass."""
    assert build_rationale(_cell(calibrated=True)).calibrated is True
    assert build_rationale(_cell(calibrated=False)).calibrated is False


def test_deterministic_equal_factors() -> None:
    """Two calls on the same cell yield equal factors (deterministic)."""
    cell = _cell(verdict="retracted", retracted_count=3, has_mentions=True)
    assert build_rationale(cell).factors == build_rationale(cell).factors


def test_unknown_verdict_non_empty_headline_no_raise() -> None:
    """An unknown verdict yields a non-empty headline and does not raise."""
    r = build_rationale(_cell(verdict="who_knows"))
    assert isinstance(r.headline, str)
    assert r.headline


def test_as_dict_round_trips_fields() -> None:
    """as_dict() exposes verdict, headline, factors (list), calibrated."""
    r = build_rationale(_cell(verdict="genuine_gap", calibrated=False))
    d = r.as_dict()
    assert d["verdict"] == "genuine_gap"
    assert d["headline"] == r.headline
    assert isinstance(d["factors"], list)
    assert d["factors"] == r.factors
    assert d["calibrated"] is False


def test_dataclass_type_and_frozen() -> None:
    """build_rationale returns a frozen AbsenceRationale."""
    r = build_rationale(_cell())
    assert isinstance(r, AbsenceRationale)
    import dataclasses

    assert dataclasses.is_dataclass(r)


def test_missing_keys_take_neutral_defaults() -> None:
    """An empty cell dict does not raise and has recall/miss factors."""
    r = build_rationale({})
    assert r.verdict == ""
    assert r.calibrated is False
    assert any("recall" in f for f in r.factors)


def test_recall_factor_reflects_different_value() -> None:
    """A different recall value shows up formatted in a factor."""
    r = build_rationale(_cell(recall=0.05))
    assert any("0.05" in f for f in r.factors)
