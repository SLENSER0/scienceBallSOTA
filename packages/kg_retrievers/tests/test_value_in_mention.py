"""[DE] Tests for the measurable-value-in-mention detector (spec §33, port of A7).

The detector is the offline, LLM-optional signal that fixes the mention-vs-value confusion:
a sentence that STATES a value (a number, no negation cue) vs one that merely NAMES a
property ("не измеряли; запланировано"). Runs fully offline, no LLM.
"""

from __future__ import annotations

from kg_retrievers.value_in_mention import value_present_in_text


def test_value_stated_in_prose_is_detected():
    txt = (
        "Для сплава X старение при 180 °C также повысило твердость до 128.4 HV "
        "по сравнению с исходным состоянием."
    )
    assert value_present_in_text(txt, ["твердость", "HV"]) is True


def test_value_stated_in_english_prose_is_detected():
    txt = "Aging at 180 C also raised the Vickers hardness to 128 HV versus the as-built state."
    assert value_present_in_text(txt, ["hardness", "hv"]) is True


def test_named_but_not_measured_is_rejected():
    txt = (
        "Параметр «относительное удлинение» для сплава X в данной кампании не измеряли; "
        "измерение запланировано в будущей работе."
    )
    assert value_present_in_text(txt, ["относительное удлинение", "удлинение"]) is False


def test_named_but_not_measured_english_is_rejected():
    txt = "Elongation was not measured in this campaign; it is planned for future work."
    assert value_present_in_text(txt, ["elongation"]) is False


def test_alias_filter_isolates_the_property():
    # a value for a DIFFERENT property must not count as this property's value
    txt = "Предел прочности вырос до 512 MPa. Модуль упругости не измеряли."
    assert value_present_in_text(txt, ["модуль упругости"]) is False
    assert value_present_in_text(txt, ["предел прочности"]) is True


def test_cross_property_english():
    txt = "Yield strength reached 512 MPa. Elastic modulus was not determined."
    assert value_present_in_text(txt, ["elastic modulus"]) is False
    assert value_present_in_text(txt, ["yield strength"]) is True


def test_empty_and_valueless_text():
    assert value_present_in_text("", ["hv"]) is False
    assert value_present_in_text("Свойство обсуждалось качественно.", ["свойство"]) is False


def test_negation_cue_beats_a_stray_number():
    # a number present but the sentence explicitly says it was NOT measured
    txt = "Твердость (образец 3) не измеряли в этой кампании."
    assert value_present_in_text(txt, ["твердость"]) is False


def test_empty_alias_list_returns_false_not_match_all():
    # Finding A: an empty alias list means the property is un-locatable; the detector must
    # NOT fall through to "any numbered sentence counts".
    txt = "Предел прочности вырос до 512 MPa."
    assert value_present_in_text(txt, []) is False
    # None (no filter at all) is a distinct, intentional mode and still matches
    assert value_present_in_text(txt, None) is True


def test_negation_cue_is_word_boundary_anchored():
    # Finding B: "not" cues are word-boundary anchored, so "notably" does not fire "not".
    txt = "Твердость notably выросла до 128 HV в состаренном образце."
    assert value_present_in_text(txt, ["твердость", "hv"]) is True


def test_clause_level_deferral_is_a_known_false_negative():
    # Finding B (documented limit): sentence-scoped negation over-suppresses when one clause
    # states a value and another defers. Pinned so a future clause-level fix flips it knowingly.
    txt = "Модуль упругости 110 ГПа, старение не проводили."
    assert value_present_in_text(txt, ["модуль упругости"]) is False
