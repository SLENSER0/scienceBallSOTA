"""§12.4 tests: Fox & Shaw CombSUM/CombMNZ/CombANZ/CombMED score-combination.

Ручной hand-checkable набор по всем 9 утверждениям спецификации.
"""

from __future__ import annotations

import pytest

from kg_retrievers.comb_fusion import CombResult, _minmax_per_list, comb_fuse


def _by_id(results: list[CombResult]) -> dict[str, CombResult]:
    return {item.doc_id: item for item in results}


def test_minmax_rescales_each_list_to_unit_interval() -> None:
    # §12.4: a=10 → 1.0 (max), b=0 → 0.0 (min) в обоих списках.
    assert _minmax_per_list({"a": 10, "b": 0}) == {"a": 1.0, "b": 0.0}
    assert _minmax_per_list({"a": 5, "b": 0}) == {"a": 1.0, "b": 0.0}


def test_assertion_1_combsum_after_minmax() -> None:
    rankings = {"dense": {"a": 10, "b": 0}, "sparse": {"a": 5, "b": 0}}
    by_id = _by_id(comb_fuse(rankings, method="combsum"))
    assert by_id["a"].score == 2.0
    assert by_id["b"].score == 0.0
    # per_source нормализован: a=1.0 в каждом списке, b=0.0.
    assert by_id["a"].per_source == {"dense": 1.0, "sparse": 1.0}


def test_assertion_2_combmnz_two_lists() -> None:
    rankings = {"dense": {"a": 10, "b": 0}, "sparse": {"a": 5, "b": 0}}
    by_id = _by_id(comb_fuse(rankings, method="combmnz"))
    # CombSUM(a)=2.0, в 2 списках → 2.0 * 2 = 4.0.
    assert by_id["a"].score == 4.0


def test_assertion_3_combmnz_single_list_equals_combsum() -> None:
    # Документ c присутствует только в одном списке → hit_count=1 → *1.
    rankings = {"dense": {"a": 10, "c": 4}, "sparse": {"a": 5}}
    combsum = _by_id(comb_fuse(rankings, method="combsum"))
    combmnz = _by_id(comb_fuse(rankings, method="combmnz"))
    assert combmnz["c"].hit_count == 1
    assert combmnz["c"].score == combsum["c"].score * 1


def test_assertion_4_combanz_divides_by_hit_count() -> None:
    rankings = {"dense": {"a": 10, "b": 0}, "sparse": {"a": 5, "b": 0}}
    by_id = _by_id(comb_fuse(rankings, method="combanz"))
    # CombSUM(a)=2.0 / hit_count 2 = 1.0.
    assert by_id["a"].score == 1.0


def test_assertion_5_combmed_median_of_normalized() -> None:
    rankings = {"dense": {"a": 10, "b": 0}, "sparse": {"a": 5, "b": 0}}
    by_id = _by_id(comb_fuse(rankings, method="combmed"))
    # median({1.0, 1.0}) = 1.0.
    assert by_id["a"].score == 1.0


def test_assertion_6_hit_count_field() -> None:
    rankings = {"dense": {"a": 10, "b": 0}, "sparse": {"a": 5, "b": 0}}
    by_id = _by_id(comb_fuse(rankings, method="combsum"))
    assert by_id["a"].hit_count == 2


def test_assertion_7_sorted_desc_then_id_asc() -> None:
    rankings = {"dense": {"a": 10, "b": 0}, "sparse": {"a": 5, "b": 0}}
    results = comb_fuse(rankings, method="combsum")
    # a (score 2.0) precedes b (score 0.0).
    assert [item.doc_id for item in results] == ["a", "b"]


def test_assertion_7_tie_break_by_doc_id() -> None:
    # Равные оценки → сортировка по doc_id по возрастанию.
    rankings = {"dense": {"z": 5, "y": 5}}
    results = comb_fuse(rankings, method="combsum")
    # Оба нормализуются в 0.0 (равные значения) → tie → y перед z.
    assert [item.doc_id for item in results] == ["y", "z"]


def test_assertion_8_unknown_method_raises() -> None:
    with pytest.raises(ValueError):
        comb_fuse({"dense": {"a": 1.0}}, method="bogus")


def test_assertion_9_as_dict_round_trips_all_fields() -> None:
    rankings = {"dense": {"a": 10, "b": 0}, "sparse": {"a": 5, "b": 0}}
    by_id = _by_id(comb_fuse(rankings, method="combsum"))
    payload = by_id["a"].as_dict()
    assert payload == {
        "doc_id": "a",
        "score": 2.0,
        "hit_count": 2,
        "per_source": {"dense": 1.0, "sparse": 1.0},
    }
    # per_source — независимая копия (мутация не затрагивает dataclass).
    payload["per_source"]["dense"] = 99.0
    assert by_id["a"].per_source["dense"] == 1.0


def test_minmax_empty_and_flat_lists() -> None:
    assert _minmax_per_list({}) == {}
    # Все значения равны → 0.0 каждому (нет разброса).
    assert _minmax_per_list({"a": 3, "b": 3}) == {"a": 0.0, "b": 0.0}
