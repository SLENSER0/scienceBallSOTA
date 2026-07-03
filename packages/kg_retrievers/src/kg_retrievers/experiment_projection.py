"""Experiment Explorer mini-graph projection (§17.12 / §5.2.5).

RU: Строит цепочку мини-графа, синхронизированную с одной выбранной строкой
эксперимента: ``Experiment -> Sample -> Material -> ProcessingRegime -> Property``.
Обход идёт по типизированным рёбрам схемы (``HAS_SAMPLE`` / ``OF_MATERIAL`` /
``PROCESSED_BY`` / ``MEASURED_PROPERTY``); при отсутствии канонического типа берётся
любой сосед с меткой нужной стадии. Нерешаемые стадии пропускаются в ``chain`` и
попадают в ``missing_stages``, а рёбра по-прежнему связывают решённые стадии.
EN: Builds the mini-graph chain synced to one selected experiment row:
``Experiment -> Sample -> Material -> ProcessingRegime -> Property``. Walking follows
the schema's typed edges (``HAS_SAMPLE`` / ``OF_MATERIAL`` / ``PROCESSED_BY`` /
``MEASURED_PROPERTY``), falling back to any neighbor carrying the target stage label.
Unresolvable stages are skipped in ``chain`` and recorded in ``missing_stages`` while
the remaining edges still connect the resolved stages.

Kuzu note: custom node props are NOT queryable columns — ``label`` is a base column, so
neighbours are filtered on ``b.label`` and the display ``name`` is read via ``get_node``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kg_retrievers.graph_store import KuzuGraphStore

# §5.2.5 fixed stage order for the Experiment Explorer chain.
CHAIN_ORDER: tuple[str, ...] = (
    "Experiment",
    "Sample",
    "Material",
    "ProcessingRegime",
    "Property",
)

# §17.12 canonical typed edge leading INTO each downstream stage (per schema).
_STAGE_EDGE: dict[str, str] = {
    "Sample": "HAS_SAMPLE",
    "Material": "OF_MATERIAL",
    "ProcessingRegime": "PROCESSED_BY",
    "Property": "MEASURED_PROPERTY",
}


@dataclass(frozen=True)
class ExperimentProjection:
    """Frozen §5.2.5 mini-graph projection for one experiment row (§17.12).

    ``chain`` holds one node dict per resolvable stage (``{stage, id, name}``);
    ``edges`` link consecutive resolved stages (``{source, target, type}``);
    ``missing_stages`` lists the CHAIN_ORDER stages that could not be resolved.
    """

    experiment_id: str
    chain: tuple[dict, ...]
    edges: tuple[dict, ...]
    missing_stages: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """camelCase projection for the UI / trace round-trip (§17.12, house style)."""
        return {
            "experimentId": self.experiment_id,
            "chain": [dict(node) for node in self.chain],
            "edges": [dict(edge) for edge in self.edges],
            "missingStages": list(self.missing_stages),
        }


def _node_name(store: KuzuGraphStore, node_id: str) -> str:
    """Display name of a node, falling back to its id (§17.12)."""
    node = store.get_node(node_id)
    if node:
        name = node.get("name") or node.get("canonical_name")
        if name:
            return str(name)
    return node_id


def _resolve_stage(store: KuzuGraphStore, from_id: str, stage: str) -> tuple[str, str, str] | None:
    """Resolve the next ``stage`` node reachable from ``from_id`` (§17.12).

    RU: Возвращает ``(node_id, edge_type, name)`` соседа с меткой ``stage``. Предпочитается
    канонический тип ребра из :data:`_STAGE_EDGE`; иначе берётся первый (по ``id``) сосед
    нужной стадии, а его фактический тип ребра используется как ``edge_type``.
    EN: Returns ``(node_id, edge_type, name)`` of a neighbour labelled ``stage``. The
    canonical edge type from :data:`_STAGE_EDGE` is preferred; otherwise the first
    neighbour (by ``id``) of the stage is used with its actual edge type.
    """
    expected = _STAGE_EDGE[stage]
    rows = store.rows(
        "MATCH (a:Node {id:$id})-[r:Rel]->(b:Node) WHERE b.label = $lbl "
        "RETURN b.id, r.type ORDER BY b.id",
        {"id": from_id, "lbl": stage},
    )
    if not rows:
        return None
    for bid, rtype in rows:
        if rtype == expected:
            return str(bid), str(rtype), _node_name(store, str(bid))
    bid, rtype = rows[0]
    return str(bid), str(rtype), _node_name(store, str(bid))


def build_experiment_projection(
    store: KuzuGraphStore, experiment_id: str
) -> ExperimentProjection | None:
    """Build the §5.2.5 chain for ``experiment_id`` or ``None`` if it is absent (§17.12).

    RU: Возвращает ``None``, если узел эксперимента отсутствует. Иначе обходит стадии
    :data:`CHAIN_ORDER`, начиная от корня-эксперимента; каждая следующая стадия ищется от
    последнего решённого узла. Нерешённые стадии пропускаются в ``chain`` и попадают в
    ``missing_stages``, оставшиеся рёбра связывают решённые стадии подряд.
    EN: Returns ``None`` when the experiment node is absent. Otherwise walks the
    :data:`CHAIN_ORDER` stages from the experiment root; each next stage is searched from
    the last resolved node. Unresolved stages are skipped in ``chain`` and added to
    ``missing_stages`` while the remaining edges still connect resolved stages in order.
    """
    root = store.get_node(experiment_id)
    if root is None:
        return None

    chain: list[dict] = [
        {"stage": CHAIN_ORDER[0], "id": experiment_id, "name": _node_name(store, experiment_id)}
    ]
    edges: list[dict] = []
    missing: list[str] = []
    current_id = experiment_id
    for stage in CHAIN_ORDER[1:]:
        resolved = _resolve_stage(store, current_id, stage)
        if resolved is None:
            missing.append(stage)
            continue
        node_id, edge_type, name = resolved
        chain.append({"stage": stage, "id": node_id, "name": name})
        edges.append({"source": current_id, "target": node_id, "type": edge_type})
        current_id = node_id

    return ExperimentProjection(
        experiment_id=experiment_id,
        chain=tuple(chain),
        edges=tuple(edges),
        missing_stages=tuple(missing),
    )
