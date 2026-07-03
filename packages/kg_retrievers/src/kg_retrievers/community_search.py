"""GraphRAG global & local search over communities (§11.7 / Mode C).

Thin, offline-safe wrappers on top of :func:`kg_retrievers.community.
detect_communities`:

- **global search** answers thematic/aggregate questions ("what are the main
  technology clusters for water treatment?") by scoring each community *summary*
  against the query and map-reducing the top ones into one evidence-linked
  answer.
- **local search** answers entity-centric questions by gathering a seed entity's
  community + immediate neighbours.

Scoring is deterministic term overlap (no LLM needed); an OSS LLM can enrich the
prose downstream. GraphRAG is deliberately *not* the sole retrieval core (§11.12)
— this complements the hybrid retriever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kg_common import get_logger
from kg_retrievers.community import detect_communities
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("community_search")
_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "") if len(t) >= 3}


@dataclass
class CommunityHit:
    community_id: int
    score: float
    summary: str
    top_entities: list[str]
    member_ids: list[str] = field(default_factory=list)


@dataclass
class GlobalAnswer:
    query: str
    answer: str
    communities: list[CommunityHit] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "answer": self.answer,
            "communities": [c.__dict__ for c in self.communities],
            "evidence_ids": self.evidence_ids,
        }


def _ensure_summaries(store: KuzuGraphStore) -> list[dict]:
    """Return existing community summaries, detecting communities if none exist yet."""
    rows = store.rows(
        "MATCH (f:Node) WHERE f.label='Finding' AND f.community_id IS NOT NULL "
        "RETURN f.community_id, f.text",
        {},
    )
    if rows:
        return [{"community_id": cid, "summary": text} for cid, text in rows]
    return detect_communities(store).summaries


def _members_named(store: KuzuGraphStore, cid: int) -> list[tuple[str, str]]:
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id=$c AND n.label<>'Finding' "
        "RETURN n.id, coalesce(n.name,''), coalesce(n.aliases_text,''), coalesce(n.domain,'')",
        {"c": cid},
    )
    # searchable name text = name + aliases + domain
    return [(r[0], " ".join(str(x) for x in (r[1], r[2], r[3]))) for r in rows]


def _members(store: KuzuGraphStore, cid: int) -> list[str]:
    return [mid for mid, _ in _members_named(store, cid)]


def global_search(store: KuzuGraphStore, query: str, *, limit: int = 3) -> GlobalAnswer:
    """Score community summaries against *query*, map-reduce the top ones."""
    q = _tokens(query)
    scored: list[CommunityHit] = []
    for s in _ensure_summaries(store):
        cid = int(s["community_id"])
        text = s.get("summary") or ""
        named = _members_named(store, cid)
        # match the query against the summary *and* every member's name/alias/domain,
        # so thematic terms hit the cluster even if absent from the 5-name summary.
        searchable = _tokens(text) | {t for _, nm in named for t in _tokens(nm)}
        overlap = len(q & searchable)
        if overlap == 0:
            continue
        member_ids = [mid for mid, _ in named]
        names = [(store.get_node(m) or {}).get("name", m) for m in member_ids[:8]]
        scored.append(
            CommunityHit(
                community_id=cid,
                score=overlap / (len(q) or 1),
                summary=text,
                top_entities=names,
                member_ids=member_ids,
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    top = scored[:limit]
    if top:
        answer = "Обобщение по релевантным кластерам знаний:\n" + "\n".join(
            f"• {c.summary}" for c in top
        )
    else:
        answer = "В графе нет кластеров, релевантных запросу (data gap)."
    return GlobalAnswer(
        query=query,
        answer=answer,
        communities=top,
        evidence_ids=[m for c in top for m in c.member_ids[:5]],
    )


def local_search(store: KuzuGraphStore, seed: str, *, limit: int = 15) -> dict:
    """Entity-centric context: the seed's community members + direct neighbours."""
    node = store.get_node(seed)
    if node is None:
        rows = store.rows(
            "MATCH (n:Node) WHERE toLower(n.name)=toLower($s) RETURN n.id LIMIT 1", {"s": seed}
        )
        if not rows:
            return {"seed": seed, "found": False, "members": [], "neighbors": []}
        seed = rows[0][0]
        node = store.get_node(seed)

    cid = (node or {}).get("community_id")
    members = _members(store, int(cid))[:limit] if cid is not None else []
    neigh = store.rows(
        "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) WHERE m.label<>'Chunk' RETURN DISTINCT m.id LIMIT $k",
        {"id": seed, "k": limit},
    )
    return {
        "seed": seed,
        "found": True,
        "community_id": cid,
        "members": members,
        "neighbors": [r[0] for r in neigh],
    }
