"""Query-time mention resolver — the §8.8 ``resolve_mention`` cascade.

The agent's grounding node (§7.6 Node 3) needs to turn a raw surface form —
``"AA2024"``, a typo, a Russian склонение, a semantic paraphrase — into a
canonical entity id with a confidence. §8.8 specifies this as a **cascade**:

    exact alias  →  Neo4j fulltext (``entity_name_index``)
                 →  vector search (``entity_embedding_index``)
                 →  Splink candidate scoring

and a return in the §7.3 ``EntityMention`` shape
``{ text, canonical_id, entity_type, confidence }``.

Rather than reimplement any tier, this module *composes the pieces that already
ship*:

* **alias** — :class:`kg_retrievers.alias_index.AliasIndex` (folded exact map +
  token-overlap search, the in-memory equivalent of the fulltext index, §8.4);
* **fulltext** — :func:`kg_retrievers.fulltext_query.build_entity_query` against
  the live Neo4j ``entity_name_index`` (server profile), with a graceful
  fall-back to the AliasIndex token search when the index is absent (embedded
  profile / fresh graph);
* **vector** — the same node-embedding path the ``/similar-embeddings`` router
  uses (:func:`kg_retrievers.entity_index._entity_text` +
  :func:`kg_retrievers.embeddings.embed_one` + cosine, or a populated
  :class:`EntityVectorIndex`), i.e. ``entity_embedding_index`` semantics;
* **Splink** — the deterministic per-type ER scorer
  (:func:`kg_er.deterministic.pair_score` over
  :func:`kg_er.features.build_row`), which is exactly the small-N path
  ``kg_er.resolve`` itself selects (§8.5) — it re-ranks the fulltext/vector
  candidates against the mention and supplies the final confidence.

Read-only: nothing here mutates the graph or any index.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from kg_common import get_logger
from kg_retrievers.alias_index import AliasIndex
from kg_retrievers.embeddings import embed, embed_one
from kg_retrievers.entity_index import _entity_text
from kg_retrievers.fulltext_query import build_entity_query
from kg_schema.labels import ENTITY_LABELS
from kg_schema.vector_index_spec import cosine

_log = get_logger("api.mention_resolver")

# Entity types that have an ER feature builder + deterministic scorer (§8.5).
_ER_TYPES = ("Material", "Alloy", "Equipment", "Person", "Lab", "ResearchTeam")

_ENTITY_LABELS: list[str] = sorted(str(label) for label in ENTITY_LABELS)

# Below this pair score the Splink tier is treated as "no confident match" and we
# fall back to the vector/fulltext similarity as the confidence (§8.7 review band).
_SPLINK_MIN = 0.5

# In-process node-embedding matrix cache (mirrors the /similar-embeddings router):
#   db_path -> {signature, ids, names, labels, vectors, index}
# Rebuilt when the entity-node count changes (cheap signature).
_MATRIX: dict[str, dict[str, Any]] = {}

# In-process AliasIndex cache (mirrors _MATRIX and the /entities/resolve router's
# _alias_cache): db_path -> {signature, index}. Кэш индекса алиасов по db_path.
# Rebuilt when the entity-node count changes so an ingestion refreshes it while
# repeated resolve_mention calls over a static graph reuse the same index.
_ALIAS_INDEX: dict[str, dict[str, Any]] = {}


def _alias_index(store: Any) -> AliasIndex:
    """Cached :class:`AliasIndex` for ``store`` (§8.4), rebuilt only on graph change.

    ``AliasIndex.build_from_store`` scans every entity node and folds all surfaces;
    doing that on every :func:`resolve_mention` call rebuilds an identical index when
    the graph has not changed. This memoizes it by ``db_path`` and invalidates on a
    cheap entity-count signature — the same pattern :func:`_matrix` and the search
    router already use — so it stays correct after ingestion. Any failure computing
    the signature falls back to an uncached build (original behavior).
    """
    key = str(getattr(store, "db_path", "default"))
    try:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label IN $labels RETURN count(n)",
            {"labels": _ENTITY_LABELS},
        )
        signature = int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0
    except Exception as exc:  # non-graph store / query error — do not cache
        _log.debug("mention_resolver.alias_signature_unavailable", error=str(exc)[:160])
        return AliasIndex.build_from_store(store)
    cached = _ALIAS_INDEX.get(key)
    if cached is not None and cached["signature"] == signature:
        return cached["index"]
    index = AliasIndex.build_from_store(store)
    _ALIAS_INDEX[key] = {"signature": signature, "index": index}
    return index


# --------------------------------------------------------------------------- #
# Result type (§7.3 EntityMention — superset with candidates for the UI/agent)  #
# --------------------------------------------------------------------------- #
@dataclass
class EntityMention:
    """§7.3 grounding result for one surface form."""

    text: str
    canonical_id: str | None
    entity_type: str | None
    confidence: float
    tier: str  # which cascade tier decided: alias|fulltext|vector|splink|none
    name: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "canonical_id": self.canonical_id,
            "entity_type": self.entity_type,
            "confidence": round(float(self.confidence), 6),
            "tier": self.tier,
            "name": self.name,
            "candidates": self.candidates,
        }


# --------------------------------------------------------------------------- #
# Tier 2 — fulltext (Neo4j entity_name_index, fall back to token overlap)       #
# --------------------------------------------------------------------------- #
def _fulltext_candidates(
    store: Any, index: AliasIndex, text: str, limit: int
) -> list[tuple[str, float]]:
    """Candidates from the Neo4j fulltext index; fall back to AliasIndex.search.

    On the server profile (§8.4) we call
    ``db.index.fulltext.queryNodes('entity_name_index', <lucene>)`` with a fuzzy
    Lucene query so declined / misspelled surfaces still match. Any failure — the
    index does not exist (embedded / fresh graph), a Kuzu store, a parse error —
    falls back to the AliasIndex token-overlap search, which is the documented
    in-memory equivalent (§3.12 / :mod:`kg_retrievers.entity_fulltext`).
    """
    fq = build_entity_query(text, fuzzy=True)
    if fq.lucene:
        try:
            rows = store.rows(
                "CALL db.index.fulltext.queryNodes($idx, $q) YIELD node, score "
                "RETURN node.id AS id, score AS score LIMIT $lim",
                {"idx": fq.index, "q": fq.lucene, "lim": limit},
            )
            hits: list[tuple[str, float]] = []
            top = None
            for r in rows:
                eid = r[0]
                raw = float(r[1]) if r[1] is not None else 0.0
                if not eid:
                    continue
                top = raw if top is None else max(top, raw)
                hits.append((str(eid), raw))
            if hits:
                # Lucene scores are unbounded; normalise to (0, 1] by the top hit
                # so they compose with the cosine / alias tiers.
                scale = top or 1.0
                return [(eid, min(1.0, raw / scale)) for eid, raw in hits[:limit]]
        except Exception as exc:  # index absent / non-Neo4j store / parse error
            _log.debug("mention_resolver.fulltext_fallback", error=str(exc)[:160])
    # Embedded / fallback path: token-overlap over the folded alias surfaces.
    return index.search(text, limit)


# --------------------------------------------------------------------------- #
# Tier 3 — vector (entity_embedding_index semantics)                           #
# --------------------------------------------------------------------------- #
def _entity_index() -> Any | None:
    """A populated :class:`EntityVectorIndex`, or ``None`` if empty/unavailable."""
    try:
        from kg_retrievers.entity_index import EntityVectorIndex

        idx = EntityVectorIndex()
        if idx.count() > 0:
            return idx
    except Exception as exc:  # qdrant locked / collection missing
        _log.debug("mention_resolver.entity_index_unavailable", error=str(exc)[:160])
    return None


def _matrix(store: Any) -> dict[str, Any]:
    """Cached (ids/names/labels/vectors) matrix of entity node-embeddings (§3.13)."""
    key = str(getattr(store, "db_path", "default"))
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels "
        "AND (n.name IS NOT NULL OR n.aliases_text IS NOT NULL) RETURN n",
        {"labels": _ENTITY_LABELS},
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        node = store._node_dict(row[0])
        nid = node.get("id")
        txt = _entity_text(node)
        if not nid or not txt:
            continue
        items.append(
            {
                "id": str(nid),
                "name": node.get("name") or node.get("canonical_name") or str(nid),
                "label": node.get("label", "Entity"),
                "text": txt,
            }
        )
    signature = len(items)
    cached = _MATRIX.get(key)
    if cached is not None and cached["signature"] == signature:
        return cached

    t0 = time.perf_counter()
    vectors = embed([it["text"] for it in items]) if items else []
    record = {
        "signature": signature,
        "ids": [it["id"] for it in items],
        "names": [it["name"] for it in items],
        "labels": [it["label"] for it in items],
        "vectors": vectors,
        "index": {it["id"]: i for i, it in enumerate(items)},
    }
    _MATRIX[key] = record
    _log.info(
        "mention_resolver.matrix_built",
        entities=signature,
        seconds=round(time.perf_counter() - t0, 2),
    )
    return record


def _vector_candidates(
    store: Any, text: str, limit: int, label_filter: set[str] | None
) -> list[tuple[str, float]]:
    """Top-k entities by cosine over ``entity_embedding_index`` (§8.4 / §3.13)."""
    idx = _entity_index()
    if idx is not None:
        raw = idx.similar_entities(text, k=limit * 3 if label_filter else limit)
        out = [
            (h.id, float(h.score))
            for h in raw
            if not label_filter or h.label in label_filter
        ]
        return out[:limit]

    matrix = _matrix(store)
    if not matrix["ids"]:
        return []
    qvec = embed_one(text)
    scored: list[tuple[str, float]] = []
    for i, vec in enumerate(matrix["vectors"]):
        if label_filter and matrix["labels"][i] not in label_filter:
            continue
        scored.append((matrix["ids"][i], float(cosine(qvec, vec))))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]


# --------------------------------------------------------------------------- #
# Tier 4 — Splink (deterministic per-type ER scoring re-rank, §8.5/§8.7)        #
# --------------------------------------------------------------------------- #
def _er_mention_record(store: Any, eid: str) -> dict[str, Any] | None:
    """Pull a node as a kg_er mention record (the fields the feature builders read)."""
    node = store.get_node(eid)
    if node is None:
        return None
    return {
        "unique_id": eid,
        "name": node.get("name") or node.get("canonical_name"),
        "formula": node.get("formula") or node.get("normalized_formula"),
        "designation": node.get("designation") or node.get("designation_code"),
        "alloy_family": node.get("alloy_family"),
        "manufacturer": node.get("manufacturer"),
        "model": node.get("model") or node.get("model_code"),
        "equipment_class": node.get("equipment_class"),
        "orcid": node.get("orcid"),
        "email": node.get("email"),
        "org": node.get("org") or node.get("organization"),
        "city": node.get("city"),
        "country": node.get("country"),
        "_label": node.get("label"),
        "_name": node.get("name") or node.get("canonical_name") or eid,
    }


def _splink_rescore(
    store: Any, text: str, entity_type: str, candidate_ids: list[str]
) -> list[tuple[str, float, str]]:
    """Re-rank candidates by the deterministic ER pair score against the mention.

    This is the exact scorer ``kg_er.resolve`` runs on the small-N query path
    (§8.5): the mention becomes a synthetic feature row and each candidate is
    scored pairwise. Returns ``[(entity_id, probability, name), …]`` sorted
    high→low. Falls back to an empty list (caller keeps the vector/fulltext
    ranking) if the type has no scorer or scoring raises.
    """
    try:
        from kg_er.deterministic import pair_score
        from kg_er.features import build_row
    except Exception:  # pragma: no cover - kg_er should always import
        return []
    if entity_type not in _ER_TYPES:
        return []
    try:
        query_row = build_row(entity_type, {"unique_id": "__query__", "name": text})
    except Exception:
        return []

    scored: list[tuple[str, float, str]] = []
    for eid in candidate_ids:
        rec = _er_mention_record(store, eid)
        if rec is None:
            continue
        try:
            cand_row = build_row(entity_type, rec)
            p = float(pair_score(entity_type, query_row, cand_row))
        except Exception:
            continue
        scored.append((eid, p, str(rec.get("_name") or eid)))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


# --------------------------------------------------------------------------- #
# Public entry point                                                            #
# --------------------------------------------------------------------------- #
def resolve_mention(
    store: Any,
    text: str,
    entity_type: str | None = None,
    *,
    limit: int = 5,
) -> EntityMention:
    """Resolve a surface form to a canonical entity via the §8.8 cascade.

    ``store``   the live graph store (server profile Neo4j, or embedded Kuzu);
    ``text``    the raw mention (упоминание);
    ``entity_type`` optional label constraint (``"Material"`` …). When given it
                filters every tier; when ``None`` it is inferred from the winning
                candidate's label.

    Returns an :class:`EntityMention` whose ``candidates`` carry the ranked
    alternatives (with per-tier evidence) so the agent asks for disambiguation
    only when ambiguity blocks the answer (§7.6).
    """
    surface = (text or "").strip()
    if not surface:
        return EntityMention(text=text or "", canonical_id=None, entity_type=entity_type,
                             confidence=0.0, tier="empty")

    index = _alias_index(store)
    label_filter = {entity_type} if entity_type else None

    def _label_of(eid: str) -> str | None:
        entry = index.entry(eid)
        if entry is not None:
            return entry.label
        node = store.get_node(eid)
        return node.get("label") if node else None

    def _name_of(eid: str) -> str:
        entry = index.entry(eid)
        if entry is not None:
            return entry.name
        node = store.get_node(eid)
        return (node.get("name") or node.get("canonical_name") or eid) if node else eid

    # -- Tier 1: exact alias (confidence 1.0) --------------------------------
    exact_id = index.lookup_exact(surface)
    exact_ok = exact_id is not None and (
        entity_type is None or _label_of(exact_id) == entity_type
    )

    # -- Gather candidate pool (fulltext + vector), merge per-tier evidence ---
    pool: dict[str, dict[str, Any]] = {}

    def _add(eid: str, tier: str, score: float) -> None:
        if entity_type is not None and _label_of(eid) != entity_type:
            return
        slot = pool.setdefault(
            eid, {"id": eid, "fulltext": 0.0, "vector": 0.0, "alias": 0.0}
        )
        slot[tier] = max(slot[tier], round(float(score), 6))

    for eid, sc in _fulltext_candidates(store, index, surface, limit):
        _add(eid, "fulltext", sc)
    for eid, sc in _vector_candidates(store, surface, limit, label_filter):
        _add(eid, "vector", sc)
    if exact_id is not None:
        _add(exact_id, "alias", 1.0)

    # Infer the entity type (for the Splink scorer) from the strongest candidate.
    inferred_type = entity_type
    if inferred_type is None:
        seed_id = exact_id if exact_ok else None
        if seed_id is None and pool:
            seed_id = max(
                pool.values(),
                key=lambda s: max(s["fulltext"], s["vector"], s["alias"]),
            )["id"]
        if seed_id is not None:
            inferred_type = _label_of(seed_id)

    # -- Tier 4: Splink re-rank over the pooled candidates -------------------
    ranked_ids = sorted(
        pool.keys(),
        key=lambda e: max(pool[e]["fulltext"], pool[e]["vector"], pool[e]["alias"]),
        reverse=True,
    )
    splink = (
        _splink_rescore(store, surface, inferred_type, ranked_ids[: max(limit, 8)])
        if inferred_type
        else []
    )
    splink_by_id = {eid: p for eid, p, _ in splink}
    for eid, p, _ in splink:
        if eid in pool:
            pool[eid]["splink"] = round(float(p), 6)

    # -- Decide the winner + confidence (which tier decided) -----------------
    if exact_ok:
        best_id, confidence, tier = exact_id, 1.0, "alias"
    elif splink and splink[0][1] >= _SPLINK_MIN:
        best_id, confidence, tier = splink[0][0], splink[0][1], "splink"
    elif ranked_ids:
        best_id = ranked_ids[0]
        slot = pool[best_id]
        if slot["vector"] >= slot["fulltext"]:
            confidence, tier = slot["vector"], "vector"
        else:
            confidence, tier = slot["fulltext"], "fulltext"
        # A Splink score below threshold still informs confidence if present.
        if best_id in splink_by_id:
            confidence = max(confidence, splink_by_id[best_id])
    else:
        best_id, confidence, tier = None, 0.0, "none"

    # -- Assemble the ranked candidate list for the response -----------------
    def _combined(slot: dict[str, Any]) -> float:
        return max(
            slot.get("splink", 0.0), slot["vector"], slot["fulltext"], slot["alias"]
        )

    candidates = sorted(pool.values(), key=_combined, reverse=True)
    cand_out: list[dict[str, Any]] = []
    for slot in candidates[:limit]:
        eid = slot["id"]
        cand_out.append(
            {
                "entity_id": eid,
                "name": _name_of(eid),
                "label": _label_of(eid),
                "confidence": round(_combined(slot), 6),
                "scores": {
                    "alias": slot["alias"],
                    "fulltext": slot["fulltext"],
                    "vector": slot["vector"],
                    "splink": slot.get("splink", 0.0),
                },
            }
        )

    result = EntityMention(
        text=surface,
        canonical_id=best_id,
        entity_type=(entity_type or (_label_of(best_id) if best_id else None)),
        confidence=round(float(confidence), 6),
        tier=tier,
        name=_name_of(best_id) if best_id else None,
        candidates=cand_out,
    )
    _log.info(
        "mention_resolver.resolved",
        text=surface[:80],
        canonical_id=best_id,
        tier=tier,
        confidence=result.confidence,
        n_candidates=len(cand_out),
    )
    return result
