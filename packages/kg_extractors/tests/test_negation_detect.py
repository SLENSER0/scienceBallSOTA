"""Tests for evidence-span negation/absence detection (§6.10)."""

from __future__ import annotations

from kg_extractors.negation_detect import (
    NEGATION_TRIGGERS,
    NegationResult,
    detect_negation,
    is_positive_fact,
)


def test_no_significant_trigger() -> None:
    r = detect_negation("No significant increase in hardness")
    assert r.negated is True
    assert r.trigger == "no significant"
    assert r.scope_text == "No significant increase in hardness"


def test_not_observed_trigger() -> None:
    assert detect_negation("The effect was not observed").negated is True


def test_positive_statement_not_negated() -> None:
    r = detect_negation("Hardness increased to 148 HV")
    assert r.negated is False
    assert r.trigger is None
    assert r.scope_text == ""


def test_without_trigger() -> None:
    assert detect_negation("without any change").negated is True


def test_absence_of_trigger() -> None:
    r = detect_negation("absence of precipitates")
    assert r.negated is True
    assert r.trigger == "absence of"


def test_did_not_trigger() -> None:
    r = detect_negation("The sample did not fracture")
    assert r.negated is True
    assert r.trigger == "did not"


def test_no_change_trigger() -> None:
    r = detect_negation("There was no change in modulus")
    assert r.negated is True
    assert r.trigger == "no change"


def test_is_positive_fact_true_for_positive() -> None:
    assert is_positive_fact("Hardness increased to 148 HV") is True


def test_is_positive_fact_false_for_negated() -> None:
    assert is_positive_fact("No significant increase in hardness") is False


def test_as_dict_negated_is_real_bool() -> None:
    d = detect_negation("x").as_dict()
    assert isinstance(d["negated"], bool)
    assert d == {"negated": False, "trigger": None, "scope_text": ""}


def test_as_dict_negated_true_shape() -> None:
    d = detect_negation("not observed here").as_dict()
    assert d == {
        "negated": True,
        "trigger": "not observed",
        "scope_text": "not observed here",
    }


def test_case_insensitive_matching() -> None:
    r = detect_negation("ABSENCE OF secondary phase")
    assert r.negated is True
    assert r.trigger == "absence of"
    # scope_text preserves the original casing of the input.
    assert r.scope_text == "ABSENCE OF secondary phase"


def test_earliest_trigger_wins() -> None:
    # "without" precedes "no change" in the text, so it should be reported.
    r = detect_negation("Processed without heat, with no change observed")
    assert r.trigger == "without"


def test_scope_text_starts_at_trigger() -> None:
    r = detect_negation("Overall, no significant drop was seen")
    assert r.scope_text == "no significant drop was seen"


def test_result_is_frozen() -> None:
    r = NegationResult(negated=False, trigger=None, scope_text="")
    try:
        r.negated = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("NegationResult must be frozen")


def test_triggers_catalog_shape() -> None:
    assert "no significant" in NEGATION_TRIGGERS
    assert "absence of" in NEGATION_TRIGGERS
    assert "no change" in NEGATION_TRIGGERS
    assert all(t == t.lower() for t in NEGATION_TRIGGERS)
