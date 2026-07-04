"""Live cross-encoder / §12.9 reranker in the retrieval path (§12.9, §7.5 Node 6).

RU: Модули §12.9 (`kg_retrievers.rerank`, `rerank_api`, `rerank_explain`,
`reranker_config`) собраны, но НЕ вызывались из живого retrieval-пути agent/API.
Этот роутер включает финальный rerank-проход НАД ЖИВЫМ графом (server-профиль
Neo4j / embedded Kuzu): по запросу он строит fusion-кандидатов теми же оценщиками,
что и full-system (`kg_retrievers.scoring`: keyword + evidence_quality +
graph_proximity → `weighted_fuse`), затем прогоняет §12.9 rerank-проход
(`rerank_api.rerank_scored`) — штрафы за missing source span и low confidence —
и возвращает fusion-порядок vs reranked-порядок с покомпонентной раскладкой
(`rerank_explain.explain_rerank`).

Опциональный cross-encoder (`reranker_config`, §10.2): если модель `sentence-
transformers CrossEncoder` доступна, её скор (query, chunk_text) заменяет
fusion-скор как базу для того же penalty-прохода; при недоступности модели
пайплайн детерминированно отдаёт fusion-порядок (§12.9 «reranking optional /
if available»). Разделение ответственности (§12.5/§12.9): fusion — мягкий приор
(verified-буст уже внутри `evidence_quality_score`), rerank — финальная штрафная
корректировка, чтобы эффект не дублировался.

EN: turns the built-but-unwired §12.9 reranker on inside the live retrieval path.
Read-only over the store; no writes, no edits to existing modules.

New router — no hub edits. Wire via ``routers/__init__.py`` (see feature wiring).
"""

from __future__ import annotations

import functools
import re
import time
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/rerank", tags=["rerank"])

_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_TEXT_FIELDS = ("name", "canonical_name", "aliases_text", "text")
_CANDIDATE_LIMIT = 200
_SPAN_FIELDS = ("char_start", "char_end")


# --------------------------------------------------------------------------- #
# Live candidate retrieval (parameterized keyword-contains, same as benchmark) #
# --------------------------------------------------------------------------- #
def _tokenize(text: str | None) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def _keyword_score(node: dict[str, Any], tokens: set[str]) -> float:
    hay = _tokenize(" ".join(str(node.get(f) or "") for f in _TEXT_FIELDS))
    return len(tokens & hay) / (len(tokens) or 1)


def _candidate_nodes(store: Any, query: str, limit: int = _CANDIDATE_LIMIT) -> dict[str, dict]:
    """Nodes whose text columns CONTAIN any query token (parameterized Cypher, readonly)."""
    tokens = _tokenize(query)
    if not tokens:
        return {}
    conds: list[str] = []
    params: dict[str, Any] = {}
    for i, tok in enumerate(sorted(tokens)):
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
    try:
        for row in store.rows(cypher, params):
            nd = store._node_dict(row[0])
            nid = nd.get("id")
            if nid:
                out[str(nid)] = nd
    except Exception:
        return {}
    return out


def _has_span(node: dict[str, Any]) -> bool:
    """A hit has a source span if it carries char offsets (or table row/col, §8.3)."""
    if all(node.get(f) is not None for f in _SPAN_FIELDS):
        return True
    return node.get("table_row") is not None and node.get("table_col") is not None


def _text_of(node: dict[str, Any]) -> str:
    for f in ("text", "name", "canonical_name"):
        v = node.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _confidence_of(node: dict[str, Any]) -> float | None:
    v = node.get("confidence")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _verified(node: dict[str, Any]) -> bool:
    return node.get("verified") is True or node.get("review_status") == "accepted"


# --------------------------------------------------------------------------- #
# Optional cross-encoder singleton (§10.2 / reranker_config; graceful degrade) #
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=2)
def _load_cross_encoder(model: str) -> Any | None:
    """Lazy singleton CrossEncoder; returns ``None`` if unavailable (§12.9 optional).

    Загрузка модели ленивая и кэшируется. При отсутствии `sentence-transformers`
    или недоступности весов возвращает ``None`` → пайплайн отдаёт fusion-порядок.
    """
    try:
        from kg_retrievers.reranker_config import is_permissive_model

        if not is_permissive_model(model):
            return None
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

        return CrossEncoder(model)
    except Exception:
        return None


def _cross_encoder_scores(
    model: str, query: str, texts: list[str], batch_size: int
) -> list[float] | None:
    ce = _load_cross_encoder(model)
    if ce is None:
        return None
    try:
        pairs = [(query, t) for t in texts]
        scores = ce.predict(pairs, batch_size=batch_size)
        return [float(s) for s in scores]
    except Exception:
        return None


def _minmax(vals: list[float]) -> list[float]:
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return [1.0] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


# --------------------------------------------------------------------------- #
# Fusion → §12.9 rerank                                                        #
# --------------------------------------------------------------------------- #
def _build_hits(store: Any, query: str, nodes: dict[str, dict]) -> list[dict[str, Any]]:
    """Fusion hits (keyword + evidence_quality) with §12.9 rerank fields.

    Fusion here is the *soft prior* (§12.5/§12.9 division of responsibility): keyword
    relevance + evidence_quality (which already carries the verified boost, §12.5).
    graph_proximity is intentionally omitted from this interactive path — it needs a
    multi-hop BFS DB query per candidate and blows the chat/query latency budget
    (§15.2); the §12.9 rerank pass (span / confidence penalties, optional
    cross-encoder) is the point of this endpoint and runs over the fused prior.
    """
    from kg_retrievers.scoring import evidence_quality_score, weighted_fuse

    tokens = _tokenize(query)
    kw = {nid: s for nid, nd in nodes.items() if (s := _keyword_score(nd, tokens)) > 0}
    if not kw:
        return []
    comps: dict[str, dict[str, float]] = {
        "keyword": kw,
        "evidence_quality": {nid: evidence_quality_score(nodes[nid]) for nid in kw},
    }
    fused = weighted_fuse(comps)
    hits: list[dict[str, Any]] = []
    for f in fused:
        nd = nodes[f.id]
        hits.append(
            {
                "id": f.id,
                "score": f.score,
                "text": _text_of(nd),
                "node": nd,
                "has_span": _has_span(nd),
                "confidence": _confidence_of(nd),
                "verified": _verified(nd),
                "evidence_count": int(nd.get("evidence_count") or 0),
                "components": f.components,
                "label": nd.get("label"),
                "name": nd.get("name") or nd.get("canonical_name") or f.id,
            }
        )
    return hits


def _hit_view(hit: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "id": hit["id"],
        "rank": rank,
        "name": hit["name"],
        "label": hit["label"],
        "score": hit["score"],
        "has_span": hit["has_span"],
        "verified": hit["verified"],
        "confidence": hit["confidence"],
        "evidence_count": hit["evidence_count"],
        "components": hit.get("components", {}),
    }


class RerankResponse(BaseModel):
    query: str
    enabled: bool
    top_n: int
    candidate_count: int
    cross_encoder: dict[str, Any]
    fusion_order: list[dict[str, Any]]
    reranked_order: list[dict[str, Any]]
    summary: dict[str, Any]
    timings_ms: dict[str, float]


@router.get("/live", response_model=RerankResponse)
def rerank_live(
    q: str = Query(..., min_length=1, description="Retrieval query (RU/EN)"),
    enabled: bool = Query(True, description="§12.9 rerank on; False → deterministic fusion order"),
    top_n: int = Query(50, ge=1, le=200, description="rerank_top_n candidates (§10.2)"),
    cross_encoder: bool = Query(False, description="Use CrossEncoder score as base (if available)"),
    confidence_threshold: float = Query(0.5, ge=0.0, le=1.0),
) -> RerankResponse:
    """Run the live §12.9 rerank pass over fusion candidates and return before/after.

    Строит fusion-кандидатов над живым графом, применяет §12.9 rerank-проход
    (штрафы missing-span / low-confidence, опционально cross-encoder как база) и
    возвращает fusion-порядок vs reranked-порядок с покомпонентной раскладкой.
    При ``enabled=false`` — детерминированный passthrough (fusion-порядок).
    """
    from kg_retrievers.rerank_api import rerank_scored
    from kg_retrievers.rerank_explain import explain_rerank
    from kg_retrievers.reranker_config import default_reranker_config

    t0 = time.perf_counter()
    store = get_store()
    nodes = _candidate_nodes(store, q)
    hits = _build_hits(store, q, nodes)
    t_retrieval = (time.perf_counter() - t0) * 1000.0

    cfg = default_reranker_config()
    ce_meta: dict[str, Any] = {
        "requested": cross_encoder,
        "model": cfg.model,
        "used": False,
        "available": False,
    }

    # Optional cross-encoder: replace the fusion base score with the CE (query,text)
    # score, so the §12.9 penalty pass rides on top of the cross-encoder ranking.
    t_ce0 = time.perf_counter()
    if cross_encoder and hits:
        texts = [h["text"] for h in hits]
        ce_scores = _cross_encoder_scores(cfg.model, q, texts, cfg.batch_size)
        if ce_scores is not None:
            for h, s in zip(hits, _minmax(ce_scores), strict=False):
                h["score"] = round(s, 6)
                h["ce_score"] = s
            ce_meta.update(used=True, available=True)
        else:
            ce_meta["available"] = False
    t_ce = (time.perf_counter() - t_ce0) * 1000.0

    # Fusion order = deterministic passthrough (enabled=False) baseline.
    fusion_ranked = rerank_scored(q, hits, top_n=top_n, enabled=False)
    fusion_rank_by_id = {r.id: r.rank for r in fusion_ranked}

    t_rr0 = time.perf_counter()
    scored = rerank_scored(
        q,
        hits,
        top_n=top_n,
        enabled=enabled,
        confidence_threshold=confidence_threshold,
    )
    t_rerank = (time.perf_counter() - t_rr0) * 1000.0

    hit_by_id = {h["id"]: h for h in hits}

    fusion_order = [
        _hit_view(hit_by_id[r.id], r.rank) for r in fusion_ranked if r.id in hit_by_id
    ]

    reranked_order: list[dict[str, Any]] = []
    n_moved = 0
    n_span_promoted = 0
    for r in scored:
        h = hit_by_id.get(r.id)
        if h is None:
            continue
        prev_rank = fusion_rank_by_id.get(r.id)
        delta = (prev_rank - r.rank) if prev_rank is not None else 0
        if delta != 0:
            n_moved += 1
        if delta > 0 and (h["has_span"] or h["verified"]):
            n_span_promoted += 1
        expl = explain_rerank(h, confidence_threshold=confidence_threshold)
        view = _hit_view(h, r.rank)
        view.update(
            base_score=r.base_score,
            adjusted_score=r.adjusted_score,
            span_penalty=r.span_penalty,
            confidence_penalty=r.confidence_penalty,
            fusion_rank=prev_rank,
            rank_delta=delta,
            factors=[f.as_dict() for f in expl.factors],
        )
        reranked_order.append(view)

    summary = {
        "positions_changed": n_moved,
        "verified_or_span_promoted": n_span_promoted,
        "passthrough": not enabled,
        "identical_to_fusion": all(v["rank_delta"] == 0 for v in reranked_order),
    }

    return RerankResponse(
        query=q,
        enabled=enabled,
        top_n=top_n,
        candidate_count=len(hits),
        cross_encoder=ce_meta,
        fusion_order=fusion_order,
        reranked_order=reranked_order,
        summary=summary,
        timings_ms={
            "retrieval": round(t_retrieval, 3),
            "cross_encoder": round(t_ce, 3),
            "rerank": round(t_rerank, 3),
        },
    )


@router.get("/config")
def rerank_config() -> dict[str, Any]:
    """Return the active §12.9 reranker config + cross-encoder availability."""
    from kg_retrievers.rerank_api import (
        DEFAULT_CONFIDENCE_THRESHOLD,
        LOW_CONFIDENCE_PENALTY,
        MISSING_SPAN_PENALTY,
    )
    from kg_retrievers.reranker_config import default_reranker_config

    cfg = default_reranker_config()
    try:
        import sentence_transformers  # noqa: F401

        ce_importable = True
    except Exception:
        ce_importable = False
    return {
        "config": cfg.as_dict(),
        "penalties": {
            "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            "missing_span_penalty": MISSING_SPAN_PENALTY,
            "low_confidence_penalty": LOW_CONFIDENCE_PENALTY,
        },
        "cross_encoder_importable": ce_importable,
    }
