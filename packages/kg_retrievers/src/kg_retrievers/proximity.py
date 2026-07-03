"""Дискретная 5-уровневая близость в графе (§12.5 / §10.3).

Discrete graph proximity over :class:`KuzuGraphStore`. Unlike the smooth
hop-decay of :func:`kg_retrievers.scoring.graph_proximity_score`, this returns
one of six *exact* levels that encode **why** two nodes are close:

* ``1.0`` — прямое ребро происхождения (``SUPPORTED_BY`` / ``HAS_MEASUREMENT``)
  или тот же узел (direct provenance edge / self);
* ``0.8`` — тот же Experiment (same Experiment);
* ``0.6`` — тот же Material **и** Property (same Material *and* Property);
* ``0.4`` — тот же Document (same Document);
* ``0.2`` — то же сообщество, равный ``community_id`` (same community);
* ``0.0`` — иначе (otherwise).

Замечание про Kuzu: пользовательские свойства узла не являются колонками для
запросов, поэтому ключи принадлежности читаются из объединённого словаря узла
через :meth:`KuzuGraphStore.get_node` — один раз на узел, а не пофакторным
соединением (исключает N+1 в пакетном режиме).

Kuzu note: custom node props are not queryable columns, so membership keys are
read from the merged node dict via ``get_node`` — once per node — instead of
per-pair joins (this avoids the N+1 read pattern in :func:`proximity_context`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Прямые рёбра происхождения дают уровень 1.0 (§12.5). Direct provenance edges.
DIRECT_REL_TYPES: frozenset[str] = frozenset({"SUPPORTED_BY", "HAS_MEASUREMENT"})


@dataclass(frozen=True)
class ProximityScale:
    """Точная дискретная шкала близости (§12.5). The exact discrete proximity scale."""

    direct: float = 1.0
    same_experiment: float = 0.8
    same_material_property: float = 0.6
    same_document: float = 0.4
    same_community: float = 0.2
    unrelated: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "direct": self.direct,
            "same_experiment": self.same_experiment,
            "same_material_property": self.same_material_property,
            "same_document": self.same_document,
            "same_community": self.same_community,
            "unrelated": self.unrelated,
        }


# Единственный экземпляр шкалы (immutable). Shared immutable scale instance.
SCALE = ProximityScale()


def _shared(a: dict[str, Any], b: dict[str, Any], key: str) -> bool:
    """True iff both nodes carry a non-empty, equal value for ``key``."""
    va = a.get(key)
    vb = b.get(key)
    return va is not None and va == vb


def _level_from_nodes(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Membership tiers only (no edge lookup); the highest matching tier wins."""
    if _shared(a, b, "experiment_id"):
        return SCALE.same_experiment
    if _shared(a, b, "material_id") and _shared(a, b, "property_id"):
        return SCALE.same_material_property
    if _shared(a, b, "doc_id"):
        return SCALE.same_document
    if _shared(a, b, "community_id"):
        return SCALE.same_community
    return SCALE.unrelated


def _direct_ids(store: KuzuGraphStore, node_id: str) -> set[str]:
    """Ids joined to ``node_id`` by a direct provenance edge (either direction)."""
    rows = store.rows(
        "MATCH (n:Node {id:$id})-[r:Rel]-(m:Node) WHERE r.type IN $types RETURN DISTINCT m.id",
        {"id": node_id, "types": list(DIRECT_REL_TYPES)},
    )
    return {r[0] for r in rows}


def proximity_level(store: KuzuGraphStore, id_a: str, id_b: str) -> float:
    """Discrete proximity of ``id_a`` and ``id_b`` on the §12.5 scale (symmetric)."""
    if not id_a or not id_b:
        return SCALE.unrelated
    if id_a == id_b:
        return SCALE.direct
    if id_b in _direct_ids(store, id_a):
        return SCALE.direct
    a = store.get_node(id_a)
    b = store.get_node(id_b)
    if a is None or b is None:
        return SCALE.unrelated
    return _level_from_nodes(a, b)


def proximity_context(
    store: KuzuGraphStore, seed: str, candidates: Iterable[str]
) -> dict[str, float]:
    """Batch ``seed``→candidate proximity as ``{candidate_id: level}`` (§12.5).

    Single pass: the seed node and its direct edges are read once, then each
    candidate node is read once via ``get_node`` — no per-pair N+1 traversal.
    """
    seed_node = store.get_node(seed)
    direct = _direct_ids(store, seed)
    out: dict[str, float] = {}
    for cid in candidates:
        if not cid:
            continue
        if cid == seed or cid in direct:
            out[cid] = SCALE.direct
        elif seed_node is None:
            out[cid] = SCALE.unrelated
        else:
            cnode = store.get_node(cid)
            out[cid] = SCALE.unrelated if cnode is None else _level_from_nodes(seed_node, cnode)
    return out
