"""Hand-checkable tests for raw KG defect rates (§23.24)."""

from __future__ import annotations

from kg_eval.graph_defect_rates import DefectRates, scan


def test_orphan_rate_one_of_three() -> None:
    # 3 узла, ребро a->b; узел c не участвует ни в src, ни в dst -> orphan 1/3.
    nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = [{"src": "a", "dst": "b"}]
    rates = scan(nodes, edges)
    assert rates.n_nodes == 3
    assert rates.orphan_rate == 1 / 3


def test_duplicate_entity_rate_two_same_measurements() -> None:
    # Два Measurement с одинаковыми label+name -> 1 группа, 1 дубликат из 2 узлов.
    nodes = [
        {"id": "m1", "label": "Measurement", "name": "hardness"},
        {"id": "m2", "label": "Measurement", "name": "hardness"},
    ]
    rates = scan(nodes, [])
    assert rates.duplicate_entity_rate == 1 / rates.n_nodes  # == 0.5


def test_no_duplicates_is_zero() -> None:
    nodes = [
        {"id": "x", "label": "Material", "name": "steel"},
        {"id": "y", "label": "Material", "name": "iron"},
    ]
    assert scan(nodes, []).duplicate_entity_rate == 0.0


def test_missing_unit_rate_over_measurements_only() -> None:
    # 4 узла, ровно один Measurement и он без unit -> доля над Measurement = 1.0.
    nodes = [
        {"id": "e", "label": "Experiment"},
        {"id": "mat", "label": "Material", "name": "cu"},
        {"id": "m", "label": "Measurement", "name": "yield"},  # нет unit
        {"id": "s", "label": "Sample"},
    ]
    rates = scan(nodes, [])
    assert rates.n_nodes == 4
    assert rates.missing_unit_rate == 1.0


def test_missing_unit_rate_zero_when_no_measurements() -> None:
    # Ни одного Measurement -> защита от деления на ноль -> 0.0.
    nodes = [{"id": "a", "label": "Material", "name": "cu"}]
    assert scan(nodes, []).missing_unit_rate == 0.0


def test_measurement_with_blank_unit_counts_as_missing() -> None:
    # Пустой/пробельный unit трактуется как отсутствующий.
    nodes = [
        {"id": "m1", "label": "Measurement", "name": "a", "unit": "  "},
        {"id": "m2", "label": "Measurement", "name": "b", "unit": "MPa"},
    ]
    assert scan(nodes, []).missing_unit_rate == 0.5


def test_missing_baseline_rate() -> None:
    # Два Experiment, у одного есть baseline -> 1/2.
    nodes = [
        {"id": "e1", "label": "Experiment", "baseline": "ref-1"},
        {"id": "e2", "label": "Experiment"},
    ]
    rates = scan(nodes, [])
    assert rates.missing_baseline_rate == 0.5
    # Нет Experiment-узлов -> 0.0 (защита от деления).
    assert scan([{"id": "x", "label": "Material"}], []).missing_baseline_rate == 0.0


def test_empty_graph_all_zero() -> None:
    rates = scan([], [])
    assert rates.n_nodes == 0
    assert rates.orphan_rate == 0.0
    assert rates.duplicate_entity_rate == 0.0
    assert rates.missing_unit_rate == 0.0
    assert rates.missing_baseline_rate == 0.0


def test_name_normalization_case_and_space_insensitive() -> None:
    # 'Al Cu' и 'al  cu' нормализуются к одному ключу -> дубликат.
    nodes = [
        {"id": "a", "label": "Material", "name": "Al Cu"},
        {"id": "b", "label": "Material", "name": "al  cu"},
    ]
    rates = scan(nodes, [])
    assert rates.duplicate_entity_rate == 0.5


def test_as_dict_has_five_keys_rounded_4dp() -> None:
    # 3 узла, один orphan -> orphan_rate 1/3 округляется до 0.3333.
    nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = [{"src": "a", "dst": "b"}]
    d = scan(nodes, edges).as_dict()
    assert set(d) == {
        "n_nodes",
        "orphan_rate",
        "duplicate_entity_rate",
        "missing_unit_rate",
        "missing_baseline_rate",
    }
    assert d["n_nodes"] == 3
    assert d["orphan_rate"] == 0.3333


def test_defectrates_is_frozen() -> None:
    rates = DefectRates(1, 0.0, 0.0, 0.0, 0.0)
    try:
        rates.orphan_rate = 1.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("DefectRates must be frozen")
