"""§12.4 Ranking explainability: decompose fused ``component_scores`` for the UI.

The five fusion signals (§10.2) — ``dense`` / ``sparse`` / ``bm25`` /
``graph_proximity`` / ``evidence_quality`` — are already computed inside the
retrieval pipeline (``kg_retrievers.scoring.weighted_fuse``) but the per-signal
breakdown is discarded before the response leaves the gateway, so the UI can only
show one opaque ``score``. This router re-runs the same real signals over the live
store (server profile: Neo4j :8000; embedded: Kuzu) and, for every hit, returns:

* ``components``     — the min-max-normalised signal values fed into fusion;
* ``contributions``  — ``components[s] * weight[s]`` (reuses the spec-exact
  :func:`kg_retrievers.fusion_contribution.attribute`);
* ``shares``         — each signal's fraction of the fused total;
* ``dominant``       — the signal that pulled this hit up the most.

Nothing is stubbed: ``dense`` reads the entity vector index when present,
``bm25`` is a real Okapi-BM25 over the candidate set, ``sparse`` is exact
token-overlap, ``graph_proximity`` walks the graph, ``evidence_quality`` reads
provenance. Weights come from §10.2 and their sum is validated on import so a
mis-configured weight vector fails fast rather than silently skewing the panel.
"""

from __future__ import annotations

import math
import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["ranking-explain"])

_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_TEXT_FIELDS = ("name", "canonical_name", "aliases_text", "text")
_CANDIDATE_LIMIT = 200

# §10.2 fusion weights — the five signals surfaced by the explainability panel.
FUSION_WEIGHTS: dict[str, float] = {
    "dense": 0.35,
    "sparse": 0.25,
    "bm25": 0.20,
    "graph_proximity": 0.10,
    "evidence_quality": 0.10,
}

# Fail fast on a mis-configured weight vector (§12.4: validate sum == 1.0 at start).
_WEIGHT_SUM = round(sum(FUSION_WEIGHTS.values()), 6)
assert _WEIGHT_SUM == 1.0, f"fusion weights must sum to 1.0, got {_WEIGHT_SUM}"

# Human-readable labels + one-line meaning for each signal (rendered in the panel).
SIGNAL_INFO: dict[str, dict[str, str]] = {
    "dense": {
        "label": "Плотный (dense)",
        "desc": "Семантическая близость эмбеддингов запроса и кандидата.",
    },
    "sparse": {
        "label": "Разреженный (sparse)",
        "desc": "Доля токенов запроса, встретившихся в тексте кандидата.",
    },
    "bm25": {
        "label": "BM25",
        "desc": "Okapi-BM25 по тексту кандидатов (частота × редкость термина).",
    },
    "graph_proximity": {
        "label": "Близость в графе",
        "desc": "Насколько кандидат близок (в переходах) к сущностям запроса.",
    },
    "evidence_quality": {
        "label": "Качество доказательств",
        "desc": "Сила источника × уверенность, с бонусом за верификацию.",
    },
}


def _tokenize(text: str | None) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _candidate_nodes(store: Any, query: str, limit: int = _CANDIDATE_LIMIT) -> dict[str, dict]:
    """Nodes whose text columns CONTAIN any query token (parameterised Cypher)."""
    tokens = sorted(set(_tokenize(query)))
    if not tokens:
        return {}
    conds: list[str] = []
    params: dict[str, Any] = {}
    for i, tok in enumerate(tokens):
        key = f"t{i}"
        params[key] = tok
        conds.append(
            f"(lower(coalesce(n.name,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.canonical_name,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.aliases_text,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.text,'')) CONTAINS ${key})"
        )
    cypher = "MATCH (n:Node) WHERE " + " OR ".join(conds) + f" RETURN n LIMIT {int(limit)}"
    out: dict[str, dict] = {}
    for row in store.rows(cypher, params):
        nd = store._node_dict(row[0])
        nid = nd.get("id")
        if nid:
            out[str(nid)] = nd
    return out


def _doc_tokens(node: dict) -> list[str]:
    return _tokenize(" ".join(str(node.get(f) or "") for f in _TEXT_FIELDS))


def _sparse_scores(nodes: dict[str, dict], q_tokens: set[str]) -> dict[str, float]:
    """Exact query-token overlap over each node's text fields, normalised to [0,1]."""
    out: dict[str, float] = {}
    denom = len(q_tokens) or 1
    for nid, nd in nodes.items():
        out[nid] = len(q_tokens & set(_doc_tokens(nd))) / denom
    return out


def _bm25_scores(
    nodes: dict[str, dict], q_tokens: set[str], *, k1: float = 1.5, b: float = 0.75
) -> dict[str, float]:
    """Okapi-BM25 of each candidate against the query over the candidate corpus."""
    docs = {nid: _doc_tokens(nd) for nid, nd in nodes.items()}
    n = len(docs) or 1
    avgdl = (sum(len(d) for d in docs.values()) / n) or 1.0
    df: dict[str, int] = {}
    for toks in docs.values():
        for term in set(toks) & q_tokens:
            df[term] = df.get(term, 0) + 1
    idf = {
        term: math.log(1.0 + (n - df_t + 0.5) / (df_t + 0.5)) for term, df_t in df.items()
    }
    out: dict[str, float] = {}
    for nid, toks in docs.items():
        dl = len(toks) or 1
        tf: dict[str, int] = {}
        for t in toks:
            if t in q_tokens:
                tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for term, f in tf.items():
            num = f * (k1 + 1.0)
            den = f + k1 * (1.0 - b + b * dl / avgdl)
            score += idf.get(term, 0.0) * num / den
        out[nid] = score
    return out


def _dense_scores(store: Any, query: str, nodes: dict[str, dict]) -> dict[str, float]:
    """Semantic similarity from the entity vector index; 0 for all when absent (honest)."""
    try:
        from kg_retrievers.entity_index import EntityVectorIndex

        idx = EntityVectorIndex()
        if idx.count() <= 0:
            return {}
        hits = idx.similar_entities(query, k=max(len(nodes), 10))
        return {str(h.id): float(h.score) for h in hits if str(h.id) in nodes}
    except Exception:
        return {}


def _graph_proximity_scores(
    store: Any, nodes: dict[str, dict], seeds: list[str]
) -> dict[str, float]:
    from kg_retrievers.scoring import graph_proximity_score

    out: dict[str, float] = {}
    for nid in nodes:
        try:
            out[nid] = graph_proximity_score(store, nid, seeds)
        except Exception:
            out[nid] = 0.0
    return out


def _evidence_quality_scores(nodes: dict[str, dict]) -> dict[str, float]:
    from kg_retrievers.scoring import evidence_quality_score

    return {nid: evidence_quality_score(nd) for nid, nd in nodes.items()}


class ExplainRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    weights: dict[str, float] | None = None  # optional override; renormalised for display


def _resolve_weights(override: dict[str, float] | None) -> dict[str, float]:
    if not override:
        return dict(FUSION_WEIGHTS)
    merged = {s: float(override.get(s, FUSION_WEIGHTS[s])) for s in FUSION_WEIGHTS}
    total = sum(merged.values())
    if total <= 0:
        return dict(FUSION_WEIGHTS)
    return {s: v / total for s, v in merged.items()}  # keep the panel's shares meaningful


@router.get("/ranking/signals")
def ranking_signals() -> dict:
    """Static catalogue of the five fusion signals and their §10.2 weights."""
    return {
        "weights": FUSION_WEIGHTS,
        "weight_sum": _WEIGHT_SUM,
        "signals": [
            {"id": s, "weight": FUSION_WEIGHTS[s], **SIGNAL_INFO[s]} for s in FUSION_WEIGHTS
        ],
    }


@router.post("/ranking/explain")
def ranking_explain(req: ExplainRequest) -> dict:
    """Rank the query and return, per hit, the decomposed fusion ``component_scores``."""
    from kg_retrievers.fusion_contribution import attribute
    from kg_retrievers.scoring import weighted_fuse

    store = get_store()
    weights = _resolve_weights(req.weights)
    q_tokens = set(_tokenize(req.query))
    nodes = _candidate_nodes(store, req.query)
    if not nodes:
        return {
            "query": req.query,
            "weights": weights,
            "count": 0,
            "hits": [],
            "signals": [{"id": s, "weight": weights[s], **SIGNAL_INFO[s]} for s in FUSION_WEIGHTS],
        }

    sparse = _sparse_scores(nodes, q_tokens)
    # Seeds for graph proximity: the strongest sparse matches act as query anchors.
    seeds = [nid for nid, _ in sorted(sparse.items(), key=lambda p: (-p[1], p[0]))[:3]]
    components: dict[str, dict[str, float]] = {
        "dense": _dense_scores(store, req.query, nodes),
        "sparse": sparse,
        "bm25": _bm25_scores(nodes, q_tokens),
        "graph_proximity": _graph_proximity_scores(store, nodes, seeds),
        "evidence_quality": _evidence_quality_scores(nodes),
    }
    # Drop signals with no signal at all (e.g. dense index absent) so their zero
    # weight does not visually dominate the panel; renormalise the shown weights.
    active = {s: c for s, c in components.items() if c and any(v > 0 for v in c.values())}
    if not active:
        active = {"sparse": sparse}
    shown_weights = _resolve_weights({s: weights[s] for s in active})

    fused = weighted_fuse(active, shown_weights)
    hits = []
    for f in fused[: req.top_k]:
        nd = nodes[f.id]
        br = attribute(f.id, f.components, shown_weights)
        hits.append(
            {
                "id": f.id,
                "name": nd.get("name"),
                "type": nd.get("label"),
                "domain": nd.get("domain"),
                "doc_id": nd.get("doc_id"),
                "score": round(f.score, 6),
                "component_scores": {s: round(v, 4) for s, v in f.components.items()},
                "contributions": {s: round(v, 6) for s, v in br.contributions.items()},
                "shares": {s: round(v, 4) for s, v in br.shares.items()},
                "dominant": br.dominant,
                "review_status": nd.get("review_status"),
                "verified": nd.get("verified"),
            }
        )
    return {
        "query": req.query,
        "count": len(hits),
        "weights": shown_weights,
        "active_signals": list(active),
        "dense_available": bool(components["dense"]),
        "signals": [
            {"id": s, "weight": shown_weights.get(s, 0.0), **SIGNAL_INFO[s]}
            for s in FUSION_WEIGHTS
        ],
        "hits": hits,
    }
