"""Decision-history DAG for ELK.js/dagre layout (§16.9).

История решений (decision history) как ориентированный ациклический граф
(DAG), который фронтенд раскладывает через ELK.js / dagre. Узлы двух базовых
видов — *события кураторства* (curation events) и *решения* (decisions) — плюс
узлы *сущностей* (entities), создаваемые по требованию для затронутых решением
объектов. Рёбра типизированы:

* ``INCLUDES`` — решение → событие: решение агрегирует набор курирующих событий
  (по ``decision.curation_event_ids``);
* ``AFFECTS`` — решение → сущность: решение изменяет затронутую сущность (по
  ``decision.affected_entity_id`` / ``affected_entity_ids``).

Это *структурный* граф для раскладки (layout), отличный от before/after
проекции в gateway ``decision_history_view`` (§16.8), которая показывает
полевой diff одного события, а не топологию «решение включает события и влияет
на сущности».

RU/EN: событие / event, решение / decision, сущность / entity, включает /
includes, влияет / affects, узел / node, ребро / edge, дедупликация / dedupe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionDag:
    """DAG истории решений для ELK.js/dagre (§16.9).

    `nodes` — кортеж node-dict'ов ``{id, kind, label}``, где ``kind`` —
    ``'event' | 'decision' | 'entity'``; `edges` — кортеж edge-dict'ов
    ``{source, target, type}``, где ``type`` — ``'INCLUDES' | 'AFFECTS'``.
    Порядок детерминирован: сперва узлы событий, затем решений, затем сущностей
    (в порядке первого появления); рёбра — в порядке обхода решений.
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/фронтенда раскладки)."""
        return asdict(self)


def _event_id(event: Mapping[str, Any]) -> str:
    """ID события: поле ``id`` или ``event_id`` (§16.9)."""
    raw = event.get("id", event.get("event_id"))
    if raw is None:
        raise ValueError("event requires an 'id' (or 'event_id')")
    return str(raw)


def _decision_id(decision: Mapping[str, Any]) -> str:
    """ID решения: поле ``id`` или ``decision_id`` (§16.9)."""
    raw = decision.get("id", decision.get("decision_id"))
    if raw is None:
        raise ValueError("decision requires an 'id' (or 'decision_id')")
    return str(raw)


def _affected_entity_ids(decision: Mapping[str, Any]) -> list[str]:
    """Затронутые сущности решения — ``affected_entity_ids`` и/или единичный."""
    ids: list[str] = []
    many = decision.get("affected_entity_ids")
    if many:
        ids.extend(str(x) for x in many)
    single = decision.get("affected_entity_id")
    if single is not None:
        ids.append(str(single))
    return ids


def build_dag(
    events: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
) -> DecisionDag:
    """Построить decision-history DAG из событий и решений (§16.9).

    По одному event-узлу на событие и по одному decision-узлу на решение.
    Для каждого id из ``decision.curation_event_ids`` — ребро ``INCLUDES``
    решение→событие. Для каждого затронутого ``affected_entity_id`` — ребро
    ``AFFECTS`` решение→сущность; entity-узлы создаются по требованию и
    дедуплицируются (один узел на уникальный id).

    Рёбра ссылаются только на существующие id узлов: INCLUDES — на id
    события-узла, AFFECTS — на id (дедуплицированного) entity-узла. Пустой вход
    даёт пустой граф (``nodes == () and edges == ()``).
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for event in events:
        eid = _event_id(event)
        if eid in node_ids:
            continue
        node_ids.add(eid)
        label = str(event.get("label", event.get("kind", eid)))
        nodes.append({"id": eid, "kind": "event", "label": label})

    entity_edges: list[dict[str, Any]] = []
    entity_nodes: list[dict[str, Any]] = []
    entity_ids: set[str] = set()

    for decision in decisions:
        did = _decision_id(decision)
        if did not in node_ids:
            node_ids.add(did)
            label = str(decision.get("label", decision.get("kind", did)))
            nodes.append({"id": did, "kind": "decision", "label": label})

        for raw in decision.get("curation_event_ids", ()) or ():
            eid = str(raw)
            if eid in node_ids:
                edges.append({"source": did, "target": eid, "type": "INCLUDES"})

        for ent_id in _affected_entity_ids(decision):
            if ent_id not in entity_ids and ent_id not in node_ids:
                entity_ids.add(ent_id)
                entity_nodes.append({"id": ent_id, "kind": "entity", "label": ent_id})
            entity_edges.append({"source": did, "target": ent_id, "type": "AFFECTS"})

    nodes.extend(entity_nodes)
    edges.extend(entity_edges)

    return DecisionDag(nodes=tuple(nodes), edges=tuple(edges))
