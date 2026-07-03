"""Expert / lab finder for a topic — «к кому обратиться» (§24.12).

Answers the "who should we consult about X?" question over a
:class:`~kg_retrievers.graph_store.KuzuGraphStore`. Given a set of subject-matter
entity ids (a topic — say the catholyte-circulation scheme), it finds the
``Person`` / ``Lab`` / ``ResearchTeam`` nodes (эксперты / лаборатории) that are
connected to those entities through the consultative relationship types

    EXPERT_IN  — an expert declares competence in a topic (expert → topic);
    PERFORMED_BY — a study / experiment was carried out by someone (topic → expert);
    MEMBER_OF  — a person belongs to a lab / team (used when the lab itself is a topic).

Candidates are ranked by *connection count* — the number of distinct topic
entities each candidate touches — so the most broadly-relevant expert surfaces
first. The module is strictly read-only.

Kuzu note (§3 / ADR-0005): custom props set on a node land in the JSON ``props``
catch-all, not in queryable columns, so we filter and return base columns only
(``id`` / ``label`` / ``name``) and read the rest via
:meth:`KuzuGraphStore.get_node` when needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("experts")

# Node labels that can act as a consultable expert (§3.4 / §24.12).
EXPERT_LABELS: tuple[str, ...] = ("Person", "Lab", "ResearchTeam")

# Relationship types that tie an expert to a subject-matter topic (§24.12).
EXPERT_REL_TYPES: tuple[str, ...] = ("EXPERT_IN", "PERFORMED_BY", "MEMBER_OF")


@dataclass(frozen=True)
class ExpertHit:
    """One ranked expert / lab candidate for a topic (§24.12).

    ``score`` is the connection count — how many distinct topic entities this
    candidate is linked to via :data:`EXPERT_REL_TYPES`. ``topics`` lists those
    entity ids (sorted, distinct); ``type`` is the node label (``Person`` /
    ``Lab`` / ``ResearchTeam``).
    """

    id: str
    type: str
    name: str
    score: int
    topics: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "score": self.score,
            "topics": list(self.topics),
        }


def find_experts(
    store: KuzuGraphStore,
    topic_entity_ids: list[str],
    *,
    limit: int = 10,
) -> list[ExpertHit]:
    """Rank ``Person``/``Lab``/``ResearchTeam`` nodes for a topic (§24.12).

    Matches candidates connected — in either direction — to any of
    ``topic_entity_ids`` through :data:`EXPERT_REL_TYPES`, then ranks them by the
    number of distinct topic entities touched (connection count), descending, with
    a stable ``id`` tie-break. Duplicate topic ids are collapsed. An empty topic
    list yields ``[]``; an unknown topic that matches nothing also yields ``[]``.
    """
    topics = list(dict.fromkeys(topic_entity_ids))
    if not topics:
        return []
    # Undirected pattern catches EXPERT_IN (expert→topic), PERFORMED_BY
    # (topic→expert) and MEMBER_OF regardless of stored orientation; fixing the
    # topic end and the expert label keeps each qualifying edge to a single row.
    rows = store.rows(
        "MATCH (ex:Node)-[r:Rel]-(t:Node) "
        "WHERE ex.label IN $labels AND t.id IN $topics AND r.type IN $rels "
        "RETURN ex.id, ex.label, ex.name, t.id",
        {"labels": list(EXPERT_LABELS), "topics": topics, "rels": list(EXPERT_REL_TYPES)},
    )
    agg: dict[str, dict[str, Any]] = {}
    for ex_id, ex_label, ex_name, t_id in rows:
        entry = agg.setdefault(ex_id, {"type": ex_label, "name": ex_name or ex_id, "topics": set()})
        entry["topics"].add(t_id)
    hits = [
        ExpertHit(
            id=ex_id,
            type=e["type"],
            name=e["name"],
            score=len(e["topics"]),
            topics=tuple(sorted(e["topics"])),
        )
        for ex_id, e in agg.items()
    ]
    hits.sort(key=lambda h: (-h.score, h.id))
    _log.info("find_experts.done", n_topics=len(topics), n_hits=len(hits))
    return hits[:limit]


def experts_for_domain(
    store: KuzuGraphStore,
    domain: str,
    *,
    limit: int = 10,
) -> list[ExpertHit]:
    """Experts for every subject-matter entity of a domain (§24.12).

    Collects the topic entities tagged with ``domain`` (excluding expert-label
    nodes so a lab is never treated as its own topic), then delegates to
    :func:`find_experts`. An unknown / empty domain yields ``[]``.
    """
    if not domain:
        return []
    rows = store.rows(
        "MATCH (n:Node) WHERE n.domain = $domain RETURN n.id, n.label",
        {"domain": domain},
    )
    topic_ids = [nid for nid, label in rows if label not in EXPERT_LABELS]
    if not topic_ids:
        return []
    return find_experts(store, topic_ids, limit=limit)
