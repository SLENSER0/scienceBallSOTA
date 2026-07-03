"""Expert recommendation with an explanatory reason — «кого посоветовать» (§24.12).

Where :mod:`kg_retrievers.experts` answers "who is connected to *these exact topic
ids*?", this module answers the softer product question: given a loose
``query_context`` — материал / процесс / география / предметная область — *which
experts should we recommend, and why?* Each recommendation carries a short RU
``reason`` naming the dimension(s) the expert shares with the query
("общий материал: медь", "та же практика/география: russia").

The recommender is a thin, read-only layer *on top of*
:func:`kg_retrievers.experts.find_experts` / :func:`~kg_retrievers.experts.experts_for_domain`
(never editing them): for every populated context dimension it resolves a set of
*anchor* topic entities in the graph, hands those to ``find_experts`` /
``experts_for_domain`` as the candidate generator, then fuses the per-dimension
hits into one ranked list. An expert's ``score`` is the sum of the weights of the
dimensions it matched (материал is the strongest signal), so an expert sharing the
material *and* the domain out-ranks one sharing only the geography.

Kuzu note (§3 / ADR-0005): custom props live in the JSON ``props`` catch-all, so we
match/return only queryable base columns (``label`` / ``operation`` /
``practice_type`` / ``country`` / ``region`` / ``domain`` / ``material_class`` …)
and exclude expert-label nodes in Python — mirroring
:func:`~kg_retrievers.experts.experts_for_domain`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.experts import EXPERT_LABELS, experts_for_domain, find_experts
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("expert_reco")

# Context dimensions (§24.12). Names double as the accepted ``query_context`` keys.
MATERIAL = "material"
DOMAIN = "domain"
PROCESS = "process"
GEOGRAPHY = "geography"

# Per-dimension signal weight — материал is the most specific "we work on the same
# thing" signal, география/практика the least. The tuple below is already
# weight-descending so a reason built by iterating it reads strongest-first.
DIM_WEIGHT: dict[str, int] = {MATERIAL: 3, DOMAIN: 2, PROCESS: 1, GEOGRAPHY: 1}
DIM_ORDER: tuple[str, ...] = (MATERIAL, DOMAIN, PROCESS, GEOGRAPHY)

# RU reason fragment per matched dimension (§24.12 — «объяснимая рекомендация»).
_REASON_TMPL: dict[str, str] = {
    MATERIAL: "общий материал: {v}",
    DOMAIN: "та же область: {v}",
    PROCESS: "тот же процесс: {v}",
    GEOGRAPHY: "та же практика/география: {v}",
}


@dataclass(frozen=True)
class ExpertRecommendation:
    """One recommended expert with a human-readable justification (§24.12).

    ``person_id`` is the expert node id (a ``Person`` — or a ``Lab`` /
    ``ResearchTeam`` acting as a consultable unit, per :data:`EXPERT_LABELS`).
    ``score`` is the summed weight of the matched context dimensions; ``reason`` is
    the RU explanation naming those shared dimensions, strongest first.
    """

    person_id: str
    name: str
    score: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "name": self.name,
            "score": self.score,
            "reason": self.reason,
        }


def _material_anchors(store: KuzuGraphStore, material: str) -> list[str]:
    """Topic anchors for a material query — the matching ``Material`` node(s) plus
    the non-expert topics linked to them (§24.12).

    A ``Material`` matches when the (lower-cased) query term is a substring of its
    ``name`` / ``canonical_name`` / ``aliases_text`` / ``material_class``. We then
    add each material's 1-hop non-expert neighbours (TechnologySolution /
    ProcessingRegime / Measurement …) so an expert linked *through* a solution to
    the material is still reachable by :func:`find_experts`.
    """
    term = material.strip().lower()
    if not term:
        return []
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label = 'Material' "
        "RETURN n.id, n.name, n.canonical_name, n.aliases_text, n.material_class"
    )
    mat_ids = [
        nid
        for nid, name, canon, aliases, mclass in rows
        if term in " ".join(x for x in (name, canon, aliases, mclass) if x).lower()
    ]
    if not mat_ids:
        return []
    anchors: set[str] = set(mat_ids)
    for tid, tlabel in store.rows(
        "MATCH (m:Node)-[:Rel]-(t:Node) WHERE m.id IN $ids RETURN DISTINCT t.id, t.label",
        {"ids": mat_ids},
    ):
        if tlabel not in EXPERT_LABELS:
            anchors.add(tid)
    return list(anchors)


def _column_anchors(store: KuzuGraphStore, columns: tuple[str, ...], value: str) -> list[str]:
    """Non-expert topic ids where any of ``columns`` equals ``value`` (§24.12).

    Used for the ``process`` (``operation``) and ``geography``
    (``country`` / ``region`` / ``practice_type``) dimensions, which map to
    queryable base columns. Expert-label nodes are dropped so a lab is never its
    own topic (mirrors :func:`experts_for_domain`).
    """
    term = value.strip()
    if not term:
        return []
    where = " OR ".join(f"n.{c} = $t" for c in columns)
    rows = store.rows(f"MATCH (n:Node) WHERE {where} RETURN n.id, n.label", {"t": term})
    return [nid for nid, label in rows if label not in EXPERT_LABELS]


def recommend_experts(
    store: KuzuGraphStore,
    query_context: dict[str, Any],
    *,
    limit: int = 5,
) -> list[ExpertRecommendation]:
    """Recommend experts for a loose ``query_context``, each with a RU reason (§24.12).

    ``query_context`` may carry any of :data:`MATERIAL` / :data:`PROCESS` /
    :data:`GEOGRAPHY` / :data:`DOMAIN` (string values; blank / non-string / unknown
    keys are ignored). For each populated dimension we resolve anchor topics and
    reuse :func:`find_experts` / :func:`experts_for_domain` as the candidate
    generator, then fuse the hits: an expert's ``score`` is the summed weight of the
    dimensions it matched (:data:`DIM_WEIGHT`) and its ``reason`` names those shared
    dimensions, strongest first. Results are ranked by score desc, with total
    connection count then ``person_id`` as stable tie-breaks, and capped to
    ``limit``.

    An empty / all-blank context yields ``[]``; a context whose only signal matches
    nothing (unknown domain, unknown material, …) also yields ``[]``.
    """
    ctx = {
        k: v.strip()
        for k, v in (query_context or {}).items()
        if k in DIM_ORDER and isinstance(v, str) and v.strip()
    }
    if not ctx:
        return []

    # Generate more candidates per dimension than `limit`, so cross-dimension fusion
    # (which can promote a lower-ranked single-dimension hit) sees the full field.
    cap = max(limit, 1) * 20 + 20

    # (dimension, matched value, per-dimension expert hits) — each entry reuses the
    # existing experts finder as its candidate generator.
    per_dim: list[tuple[str, str, list[Any]]] = []
    if MATERIAL in ctx:
        anchors = _material_anchors(store, ctx[MATERIAL])
        per_dim.append((MATERIAL, ctx[MATERIAL], find_experts(store, anchors, limit=cap)))
    if DOMAIN in ctx:
        per_dim.append((DOMAIN, ctx[DOMAIN], experts_for_domain(store, ctx[DOMAIN], limit=cap)))
    if PROCESS in ctx:
        anchors = _column_anchors(store, ("operation",), ctx[PROCESS])
        per_dim.append((PROCESS, ctx[PROCESS], find_experts(store, anchors, limit=cap)))
    if GEOGRAPHY in ctx:
        anchors = _column_anchors(store, ("country", "region", "practice_type"), ctx[GEOGRAPHY])
        per_dim.append((GEOGRAPHY, ctx[GEOGRAPHY], find_experts(store, anchors, limit=cap)))

    # Fuse per-dimension hits into one record per expert.
    agg: dict[str, dict[str, Any]] = {}
    for dim, value, hits in per_dim:
        for h in hits:
            entry = agg.setdefault(h.id, {"name": h.name, "matched": {}, "conn": 0})
            entry["matched"].setdefault(dim, value)
            entry["conn"] += h.score

    scored: list[tuple[int, int, str, ExpertRecommendation]] = []
    for pid, e in agg.items():
        matched: dict[str, str] = e["matched"]
        score = sum(DIM_WEIGHT[d] for d in matched)
        reason = "; ".join(_REASON_TMPL[d].format(v=matched[d]) for d in DIM_ORDER if d in matched)
        rec = ExpertRecommendation(person_id=pid, name=e["name"], score=score, reason=reason)
        scored.append((score, e["conn"], pid, rec))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    out = [rec for _, _, _, rec in scored[:limit]]
    _log.info("recommend_experts.done", n_dims=len(per_dim), n_candidates=len(agg), n_out=len(out))
    return out
