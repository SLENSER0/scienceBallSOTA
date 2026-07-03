"""Golden-dataset builder + IO (§18.3/§18.6)."""

from __future__ import annotations

from pathlib import Path

from kg_eval.golden_builder import (
    GoldenQA,
    build_golden_from_seed,
    load_golden,
    save_golden,
)


def test_build_returns_at_least_three_qas() -> None:
    items = build_golden_from_seed()
    assert isinstance(items, list)
    assert len(items) >= 3
    assert all(isinstance(qa, GoldenQA) for qa in items)


def test_each_qa_has_nonempty_question_and_entities() -> None:
    for qa in build_golden_from_seed():
        assert qa.question.strip(), f"empty question for {qa.id}"
        assert len(qa.expected_entities) >= 1, f"no entities for {qa.id}"
        assert all(e.strip() for e in qa.expected_entities)


def test_from_dict_as_dict_round_trip() -> None:
    original = GoldenQA(
        id="q_x",
        question="Проверка обратного осмоса?",
        expected_entities=("reverse_osmosis", "tds"),
        expected_answer_contains=("осмос",),
        expected_gap=True,
    )
    rebuilt = GoldenQA.from_dict(original.as_dict())
    assert rebuilt == original


def test_as_dict_uses_json_native_types() -> None:
    d = build_golden_from_seed()[0].as_dict()
    assert isinstance(d["expected_entities"], list)
    assert isinstance(d["expected_answer_contains"], list)
    assert isinstance(d["expected_gap"], bool)


def test_save_load_json_round_trip(tmp_path: Path) -> None:
    items = build_golden_from_seed()
    path = tmp_path / "golden.json"
    written = save_golden(items, path)
    assert written == path and path.exists()
    loaded = load_golden(path)
    assert loaded == items


def test_expected_gap_flag_present_and_bool() -> None:
    items = build_golden_from_seed()
    assert all(isinstance(qa.expected_gap, bool) for qa in items)
    # The demo set must contain at least one true gap and one non-gap case.
    gaps = [qa.expected_gap for qa in items]
    assert any(gaps) and not all(gaps)


def test_ids_unique() -> None:
    ids = [qa.id for qa in build_golden_from_seed()]
    assert len(ids) == len(set(ids))


def test_deterministic_same_call_same_set() -> None:
    a = build_golden_from_seed()
    b = build_golden_from_seed()
    assert a == b
    # Frozen dataclasses are hashable → order + content identical.
    assert [qa.as_dict() for qa in a] == [qa.as_dict() for qa in b]


def test_ro_desalination_case_present() -> None:
    by_id = {qa.id: qa for qa in build_golden_from_seed()}
    ro = by_id["q_ro_desalination"]
    assert "reverse_osmosis" in ro.expected_entities
    assert ro.expected_gap is False
    assert any("осмос" in s for s in ro.expected_answer_contains)
