"""Локальное предсказание связей над Kuzu (§12.8, NetworkX-fallback).

Local link-prediction scores over a :class:`KuzuGraphStore`, computed from
undirected neighbour sets read with ``store.rows`` (the same read pattern as
:mod:`kg_retrievers.proximity`). These feed the *"missing links"* and
*"similar materials"* features on the NetworkX-fallback path of §12.8 — no
graph-database GDS plugin is required, the graph is scored in-process.

Для пары узлов ``a`` и ``b`` с множествами соседей ``Na`` и ``Nb`` считаем
классические индексы близости:

* ``common`` — число общих соседей ``|Na ∩ Nb|`` (common neighbours);
* ``jaccard`` — ``|Na ∩ Nb| / |Na ∪ Nb|`` (0.0 при пустом объединении);
* ``adamic_adar`` — ``Σ 1/log(deg(z))`` по общим ``z`` (Adamic/Adar);
* ``resource_allocation`` — ``Σ 1/deg(z)`` по общим ``z`` (resource allocation);
* ``preferential`` — ``deg(a) · deg(b)`` (preferential attachment).

Замечание про Kuzu: пользовательские свойства узла не являются колонками для
запросов, поэтому здесь используются только базовые колонки (``m.id``) —
идентификаторы соседей читаются напрямую, без обращения к ``props``.

Kuzu note: custom node props are not queryable columns, so only base columns
(``m.id``) are returned here — neighbour ids are read directly, never via props.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore


@dataclass(frozen=True)
class LinkScore:
    """Индексы предсказания связи для упорядоченной пары (§12.8). Link-prediction scores."""

    source: str
    target: str
    common: int
    jaccard: float
    adamic_adar: float
    resource_allocation: float
    preferential: int

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "common": self.common,
            "jaccard": self.jaccard,
            "adamic_adar": self.adamic_adar,
            "resource_allocation": self.resource_allocation,
            "preferential": self.preferential,
        }


def _neighbors(store: KuzuGraphStore, node_id: str) -> set[str]:
    """Undirected DISTINCT neighbour ids of ``node_id`` (self excluded)."""
    rows = store.rows(
        "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) WHERE m.id <> $id RETURN DISTINCT m.id",
        {"id": node_id},
    )
    return {r[0] for r in rows}


def score_pair(store: KuzuGraphStore, a: str, b: str) -> LinkScore:
    """Link-prediction indices for the pair ``(a, b)`` from neighbour sets (§12.8).

    ``common``/``jaccard``/``adamic_adar``/``resource_allocation`` are symmetric
    in ``a`` and ``b``; ``source``/``target`` preserve the call order.
    """
    na = _neighbors(store, a)
    nb = _neighbors(store, b)
    inter = na & nb
    union = na | nb

    common = len(inter)
    jaccard = common / len(union) if union else 0.0

    adamic_adar = 0.0
    resource_allocation = 0.0
    for z in inter:
        deg = len(_neighbors(store, z))
        if deg > 0:
            resource_allocation += 1.0 / deg
        if deg > 1:  # log(1) == 0 → undefined Adamic/Adar term, skip degree-1 hubs
            adamic_adar += 1.0 / math.log(deg)

    preferential = len(na) * len(nb)
    return LinkScore(
        source=a,
        target=b,
        common=common,
        jaccard=jaccard,
        adamic_adar=adamic_adar,
        resource_allocation=resource_allocation,
        preferential=preferential,
    )


def rank_candidates(
    store: KuzuGraphStore,
    seed: str,
    candidates: Iterable[str],
    *,
    key: str = "adamic_adar",
) -> list[LinkScore]:
    """Score ``seed`` against each candidate and sort desc by metric ``key`` (§12.8)."""
    scores = [score_pair(store, seed, c) for c in candidates]
    scores.sort(key=lambda s: getattr(s, key), reverse=True)
    return scores
