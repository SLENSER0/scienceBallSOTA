"""Tests for the decision-history DAG builder (§16.9).

Ручная проверка (hand-checkable): небольшие наборы событий/решений с заранее
известной топологией графа для раскладки ELK.js/dagre.
"""

from __future__ import annotations

from kg_common.storage.decision_dag import DecisionDag, build_dag


def _by_id(nodes: tuple[dict, ...]) -> dict[str, dict]:
    return {n["id"]: n for n in nodes}


def test_one_decision_including_two_events_two_includes_edges() -> None:
    """(1) решение, включающее 2 события → 2 ребра INCLUDES."""
    events = [{"id": "e1"}, {"id": "e2"}]
    decisions = [{"id": "d1", "curation_event_ids": ["e1", "e2"]}]

    dag = build_dag(events, decisions)

    includes = [e for e in dag.edges if e["type"] == "INCLUDES"]
    assert len(includes) == 2
    assert {e["target"] for e in includes} == {"e1", "e2"}
    assert all(e["source"] == "d1" for e in includes)


def test_decision_affecting_entity_one_affects_edge() -> None:
    """(2) решение, влияющее на сущность 'm1' → одно ребро AFFECTS d→m1."""
    dag = build_dag([], [{"id": "d1", "affected_entity_id": "m1"}])

    affects = [e for e in dag.edges if e["type"] == "AFFECTS"]
    assert affects == [{"source": "d1", "target": "m1", "type": "AFFECTS"}]


def test_entity_node_created_exactly_once_even_if_two_decisions_affect_it() -> None:
    """(3) entity-узел 'm1' создаётся ровно один раз при двух влияющих решениях."""
    decisions = [
        {"id": "d1", "affected_entity_id": "m1"},
        {"id": "d2", "affected_entity_id": "m1"},
    ]
    dag = build_dag([], decisions)

    entity_nodes = [n for n in dag.nodes if n["kind"] == "entity"]
    assert len(entity_nodes) == 1
    assert entity_nodes[0]["id"] == "m1"
    # оба решения всё равно дают своё ребро AFFECTS
    affects = [e for e in dag.edges if e["type"] == "AFFECTS"]
    assert len(affects) == 2
    assert {e["source"] for e in affects} == {"d1", "d2"}


def test_populated_input_has_all_three_node_kinds() -> None:
    """(4) для наполненного входа множество kind == {'event','decision','entity'}."""
    events = [{"id": "e1"}]
    decisions = [{"id": "d1", "curation_event_ids": ["e1"], "affected_entity_id": "m1"}]

    dag = build_dag(events, decisions)

    assert {n["kind"] for n in dag.nodes} == {"event", "decision", "entity"}


def test_edges_only_reference_existing_node_ids() -> None:
    """(5) все рёбра ссылаются только на существующие id узлов."""
    events = [{"id": "e1"}, {"id": "e2"}]
    decisions = [
        {"id": "d1", "curation_event_ids": ["e1", "e2"], "affected_entity_ids": ["m1", "m2"]},
        {"id": "d2", "curation_event_ids": ["e1"], "affected_entity_id": "m1"},
    ]
    dag = build_dag(events, decisions)

    node_ids = {n["id"] for n in dag.nodes}
    for edge in dag.edges:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


def test_dangling_curation_event_id_does_not_create_edge() -> None:
    """INCLUDES не создаётся для несуществующего id события (не висячее ребро)."""
    decisions = [{"id": "d1", "curation_event_ids": ["ghost"]}]
    dag = build_dag([], decisions)

    node_ids = {n["id"] for n in dag.nodes}
    assert "ghost" not in node_ids
    assert dag.edges == ()


def test_empty_inputs_yield_empty_graph() -> None:
    """(6) пустой вход → nodes == () и edges == ()."""
    dag = build_dag([], [])
    assert isinstance(dag, DecisionDag)
    assert dag.nodes == ()
    assert dag.edges == ()


def test_as_dict_first_edge_type_is_typed() -> None:
    """(7) as_dict()['edges'][0]['type'] ∈ {'INCLUDES','AFFECTS'}."""
    events = [{"id": "e1"}]
    decisions = [{"id": "d1", "curation_event_ids": ["e1"], "affected_entity_id": "m1"}]

    payload = build_dag(events, decisions).as_dict()

    assert set(payload) == {"nodes", "edges"}
    assert payload["edges"][0]["type"] in {"INCLUDES", "AFFECTS"}


def test_node_labels_prefer_explicit_then_kind_then_id() -> None:
    """label: явный 'label' > 'kind' > id (детерминированная подпись узла)."""
    events = [{"id": "e1", "label": "Merged M1↔M2"}, {"id": "e2", "kind": "split"}, {"id": "e3"}]
    dag = build_dag(events, [])
    labels = {n["id"]: n["label"] for n in dag.nodes}
    assert labels == {"e1": "Merged M1↔M2", "e2": "split", "e3": "e3"}
