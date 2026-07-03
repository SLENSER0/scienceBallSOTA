"""Hand-checked tests for §7.6/§13.15 follow-up coreference resolver.

Pure-python, no store / no LLM: drive :func:`resolve_followup` directly and assert the
exact rewritten text, the ``(pronoun, entity)`` audit trail, the carryover flag and
orjson-serialisability of :class:`Resolution`. Every expected value is spelled out so
the test is verifiable by hand (RU + EN).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import orjson
import pytest
from agent_service.followup_resolver import (
    PRONOUNS,
    Resolution,
    resolve_followup,
)


# ---------------------------------------------------------------------------
# (1) anaphoric EN question carries over the most-recent entity
# ---------------------------------------------------------------------------
def test_pronoun_question_carries_over_prior_entity() -> None:
    res = resolve_followup("How does it change?", ["Al-Cu"])
    assert "Al-Cu" in res.resolved_question
    assert res.resolved_question == "How does it change? (Al-Cu)"
    assert res.used_carryover is True


# ---------------------------------------------------------------------------
# (2) question already naming the entity is returned unchanged
# ---------------------------------------------------------------------------
def test_explicit_entity_returned_unchanged() -> None:
    res = resolve_followup("What is the phase diagram of Al-Cu?", ["Al-Cu"])
    assert res.resolved_question == "What is the phase diagram of Al-Cu?"
    assert res.substitutions == ()
    assert res.used_carryover is False


# ---------------------------------------------------------------------------
# (3) empty prior_entities: nothing to carry, question untouched
# ---------------------------------------------------------------------------
def test_empty_prior_entities_leaves_pronoun_question_unchanged() -> None:
    res = resolve_followup("How does it change?", [])
    assert res.resolved_question == "How does it change?"
    assert res.substitutions == ()
    assert res.used_carryover is False


# ---------------------------------------------------------------------------
# (4) Russian oblique anaphor ('ним') carries over under language='ru'
# ---------------------------------------------------------------------------
def test_russian_oblique_anaphor_carries_over() -> None:
    res = resolve_followup("а что с ним?", ["сталь 40Х"], language="ru")
    assert res.used_carryover is True
    assert res.resolved_question == "а что с ним? (сталь 40Х)"
    assert res.substitutions == (("ним", "сталь 40Х"),)


# ---------------------------------------------------------------------------
# (5) substitutions list exactly the pronoun matched
# ---------------------------------------------------------------------------
def test_substitutions_list_exactly_matched_pronoun() -> None:
    res = resolve_followup("How does it change?", ["Al-Cu"])
    assert res.substitutions == (("it", "Al-Cu"),)


# ---------------------------------------------------------------------------
# (6) Resolution.as_dict is orjson-serialisable and round-trips
# ---------------------------------------------------------------------------
def test_as_dict_is_orjson_serialisable() -> None:
    res = resolve_followup("How does it change?", ["Al-Cu"])
    payload = orjson.dumps(res.as_dict())
    back = orjson.loads(payload)
    assert back == {
        "resolved_question": "How does it change? (Al-Cu)",
        "substitutions": [["it", "Al-Cu"]],
        "used_carryover": True,
    }


# ---------------------------------------------------------------------------
# (7) pronoun match is case-insensitive ('It' == 'it')
# ---------------------------------------------------------------------------
def test_pronoun_match_case_insensitive() -> None:
    upper = resolve_followup("How does It change?", ["Al-Cu"])
    lower = resolve_followup("How does it change?", ["Al-Cu"])
    assert upper.used_carryover is True
    assert upper.substitutions == (("it", "Al-Cu"),)
    assert upper.resolved_question == "How does It change? (Al-Cu)"
    assert lower.used_carryover is upper.used_carryover


# ---------------------------------------------------------------------------
# non-anaphoric question with prior entity present: nothing to bind
# ---------------------------------------------------------------------------
def test_non_anaphoric_question_left_unchanged() -> None:
    res = resolve_followup("Show the melting point", ["Al-Cu"])
    assert res.resolved_question == "Show the melting point"
    assert res.substitutions == ()
    assert res.used_carryover is False


# ---------------------------------------------------------------------------
# Resolution is frozen and PRONOUNS carries both languages
# ---------------------------------------------------------------------------
def test_resolution_is_frozen() -> None:
    res = Resolution(resolved_question="x", substitutions=(), used_carryover=False)
    with pytest.raises(FrozenInstanceError):
        res.resolved_question = "y"  # type: ignore[misc]


def test_pronoun_tables_cover_ru_and_en() -> None:
    assert "it" in PRONOUNS["en"]
    assert "он" in PRONOUNS["ru"]
