"""Tests for replay-divergence comparator (§23.29).

Тесты проверяемы вручную: числа, множества цитат и ключи provenance подобраны
так, чтобы ожидаемый результат читался прямо из входа.
"""

from __future__ import annotations

from kg_eval.replay_divergence import (
    DivergenceReport,
    compare_replay,
    extract_numbers,
)


def _record(
    answer_text: str = "hardness 180.5 MPa at 2 h",
    citations: tuple[str, ...] = ("doi:a", "doi:b"),
    provenance: dict[str, str] | None = None,
) -> dict[str, object]:
    if provenance is None:
        provenance = {
            "model_version": "m1",
            "prompt_version": "p1",
            "schema_version": "s1",
            "snapshot": "snap1",
        }
    return {
        "answer_text": answer_text,
        "citations": list(citations),
        "provenance": provenance,
    }


def test_identical_dicts_yield_identical_true_all_empty() -> None:
    original = _record()
    replay = _record()
    report = compare_replay(original, replay)
    assert report.identical is True
    assert report.answer_text_changed is False
    assert report.numbers_changed == ()
    assert report.citations_added == ()
    assert report.citations_removed == ()
    assert report.provenance_changed == ()


def test_differing_answer_text_sets_flag() -> None:
    original = _record(answer_text="hardness 180.5 MPa at 2 h")
    replay = _record(answer_text="softness 180.5 MPa at 2 h")
    report = compare_replay(original, replay)
    # Числа те же — меняется только слово, значит текст изменён, числа нет.
    assert report.answer_text_changed is True
    assert report.numbers_changed == ()
    assert report.identical is False


def test_extract_numbers_in_order() -> None:
    assert extract_numbers("hardness 180.5 MPa at 2 h") == (180.5, 2.0)
    assert extract_numbers("no numbers here") == ()
    assert extract_numbers("-3.0 then +4") == (-3.0, 4.0)


def test_removed_citation_sorted_and_not_in_added() -> None:
    original = _record(citations=("doi:a", "doi:b", "doi:c"))
    replay = _record(citations=("doi:a",))
    report = compare_replay(original, replay)
    assert report.citations_removed == ("doi:b", "doi:c")
    assert report.citations_added == ()


def test_added_citation() -> None:
    original = _record(citations=("doi:a",))
    replay = _record(citations=("doi:a", "doi:z", "doi:m"))
    report = compare_replay(original, replay)
    assert report.citations_added == ("doi:m", "doi:z")
    assert report.citations_removed == ()


def test_changed_model_version_listed_in_provenance_changed() -> None:
    original = _record()
    replay = _record(
        provenance={
            "model_version": "m2",
            "prompt_version": "p1",
            "schema_version": "s1",
            "snapshot": "snap1",
        }
    )
    report = compare_replay(original, replay)
    assert report.provenance_changed == ("model_version",)
    assert report.identical is False


def test_numbers_changed_reports_stringified_pair() -> None:
    original = _record(answer_text="hardness 180.5 MPa at 2 h")
    replay = _record(answer_text="hardness 200.0 MPa at 2 h")
    report = compare_replay(original, replay)
    assert report.answer_text_changed is True
    assert report.numbers_changed == (str((180.5, 200.0)),)


def test_missing_citations_key_treated_as_empty_set() -> None:
    original = {"answer_text": "x", "provenance": {}}
    replay = {"answer_text": "x", "citations": ["doi:new"], "provenance": {}}
    report = compare_replay(original, replay)
    assert report.citations_added == ("doi:new",)
    assert report.citations_removed == ()
    # Обе стороны без пересечений: original не имеет цитат вовсе.
    report_both_missing = compare_replay({"answer_text": "x"}, {"answer_text": "x"})
    assert report_both_missing.citations_added == ()
    assert report_both_missing.citations_removed == ()
    assert report_both_missing.identical is True


def test_as_dict_identical_is_bool() -> None:
    report = compare_replay(_record(), _record())
    d = report.as_dict()
    assert isinstance(d["identical"], bool)
    assert d["identical"] is True
    assert isinstance(report, DivergenceReport)
    # Кортежи сериализуются в списки.
    assert d["numbers_changed"] == []
    assert d["citations_added"] == []


def test_number_length_mismatch_uses_none_placeholder() -> None:
    original = _record(answer_text="values 1 2 3")
    replay = _record(answer_text="values 1 2")
    report = compare_replay(original, replay)
    # Третья позиция: 3.0 против отсутствия → пара с None.
    assert report.numbers_changed == (str((3.0, None)),)
