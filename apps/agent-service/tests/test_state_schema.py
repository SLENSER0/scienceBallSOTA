"""Tests for the §13.11 LangGraph agent state schema.

Deterministic, dependency-light: exercises ``empty_state`` defaults, shallow
``merge_state`` overrides, ``as_dict``/``from_dict`` round-tripping, retry-counter
increments, defaults for missing keys, ``question`` preservation and frozen
immutability on hand-checkable RU/EN inputs.
"""

from __future__ import annotations

import dataclasses

import pytest
from agent_service.state_schema import AgentState, empty_state, merge_state


def test_empty_state_defaults() -> None:
    # empty_state fills question and leaves every other field at its default.
    s = empty_state("Как очистить сточные воды?")
    assert s.question == "Как очистить сточные воды?"
    assert s.intent is None
    assert s.preprocessed is None
    assert s.retrieval is None
    assert s.answer is None
    assert s.citations == ()
    assert s.gaps == ()
    assert s.verifier_report is None
    assert s.attempts == 0


def test_as_dict_shape() -> None:
    # as_dict emits every field; tuples render as JSON-friendly lists.
    s = empty_state("вопрос")
    assert s.as_dict() == {
        "question": "вопрос",
        "intent": None,
        "preprocessed": None,
        "retrieval": None,
        "answer": None,
        "citations": [],
        "gaps": [],
        "verifier_report": None,
        "attempts": 0,
    }


def test_merge_overrides() -> None:
    # Overrides win; untouched fields (question) carry through; a is unchanged.
    s = empty_state("q")
    s2 = merge_state(s, {"answer": "ответ", "attempts": 2})
    assert s2.answer == "ответ"
    assert s2.attempts == 2
    assert s2.question == "q"
    assert s.answer is None  # original untouched (frozen, new instance)
    assert s2 is not s


def test_merge_with_agent_state_b_wins() -> None:
    # When b is a full AgentState, its fields override a's.
    a = empty_state("qa")
    b = AgentState(question="qb", answer="ans", attempts=5)
    merged = merge_state(a, b)
    assert merged.question == "qb"
    assert merged.answer == "ans"
    assert merged.attempts == 5


def test_roundtrip_as_dict_from_dict() -> None:
    # A fully-populated state round-trips through as_dict/from_dict unchanged.
    s = AgentState(
        question="сравни методы флотации и выщелачивания",
        intent={"query_type": "comparison", "entities": ["флотация", "выщелачивание"]},
        preprocessed={"language": "ru", "is_comparison": True},
        retrieval={"passages": [{"text": "п", "score": 0.9}]},
        answer="# Ответ\nМаркдаун-текст",
        citations=({"marker": "[1]", "evidence_id": "ev1"},),
        gaps=("нет данных по режиму X",),
        verifier_report={"verified": True, "coverage": 1.0},
        attempts=3,
    )
    assert AgentState.from_dict(s.as_dict()) == s


def test_attempts_increment_via_merge() -> None:
    # The retry counter advances by merging a fresh attempts value each time.
    s = empty_state("q")
    s1 = merge_state(s, {"attempts": s.attempts + 1})
    s2 = merge_state(s1, {"attempts": s1.attempts + 1})
    assert s.attempts == 0
    assert s1.attempts == 1
    assert s2.attempts == 2


def test_from_dict_defaults_for_missing() -> None:
    # A partial mapping keeps its keys and fills the rest with defaults.
    s = AgentState.from_dict({"question": "только вопрос"})
    assert s.question == "только вопрос"
    assert s.intent is None
    assert s.answer is None
    assert s.citations == ()
    assert s.gaps == ()
    assert s.verifier_report is None
    assert s.attempts == 0


def test_from_dict_empty_mapping_all_defaults() -> None:
    # An empty mapping yields the all-default state (question == "").
    s = AgentState.from_dict({})
    assert s == AgentState()
    assert s.question == ""
    assert s.attempts == 0


def test_from_dict_coerces_lists_to_tuples() -> None:
    # citations/gaps arrive as JSON lists and become immutable tuples.
    s = AgentState.from_dict(
        {"question": "q", "citations": [{"marker": "[1]"}], "gaps": ["g1", "g2"]}
    )
    assert isinstance(s.citations, tuple)
    assert isinstance(s.gaps, tuple)
    assert s.citations == ({"marker": "[1]"},)
    assert s.gaps == ("g1", "g2")


def test_question_preserved_on_merge() -> None:
    # A merge that never touches question leaves it exactly as it was.
    s = empty_state("исходный вопрос")
    s2 = merge_state(s, {"intent": {"query_type": "factual"}, "answer": "a"})
    assert s2.question == "исходный вопрос"


def test_merge_unknown_key_raises() -> None:
    # A typo'd override key is rejected instead of being silently dropped.
    s = empty_state("q")
    with pytest.raises(ValueError, match="unknown state key"):
        merge_state(s, {"nonexistent": 1})


def test_immutability_frozen() -> None:
    # Frozen dataclass: attributes cannot be reassigned in place.
    s = empty_state("q")
    assert isinstance(s, AgentState)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.question = "new"  # type: ignore[misc]
