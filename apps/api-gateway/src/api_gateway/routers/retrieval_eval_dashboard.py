"""Retrieval-eval dashboard: hybrid vs bm25 vs dense, rerank on/off (§4.11 / §18.6).

RU: Демо-панель, доказывающая ЧИСЛАМИ, что гибридный retrieval с финальным
rerank-проходом бьёт одиночные бэкенды (bm25-only, dense-only). По «золотому»
набору (§18.6, ``kg_eval.retrieval_eval.GOLDEN``) над ЖИВЫМ графом (server-профиль
Neo4j / embedded Kuzu) прогоняются шесть ячеек — три бэкенда × {rerank off, rerank
on} — и для каждой считаются макро-усреднённые ``Recall@10`` / ``MRR`` / ``nDCG@10``
(плюс ``Precision@10`` / ``hit@10``) детерминированными измерениями. Метрики
переиспользуются дословно из :mod:`kg_eval.retrieval_metrics` (``evaluate`` /
``aggregate``), ранкеры — из существующих оценщиков ``kg_retrievers.scoring``
(``weighted_fuse``, ``graph_proximity_score``, ``evidence_quality_score``) и
rerank-проход из ``kg_retrievers.rerank.mmr_rerank`` (§12.9 MMR). Ничего нового не
переписывается — роутер только собирает матрицу и выносит вердикт.

Три бэкенда над ОДНИМ графом:

* ``bm25``   — sparse keyword-overlap only (§10.2 sparse component in isolation).
* ``dense``  — entity vector index (``kg_retrievers.entity_index``); при пустом
  индексе честно деградирует к keyword-порядку (как ``search_vector``, §10.2).
* ``hybrid`` — ``weighted_fuse`` над keyword + evidence_quality + graph_proximity
  (+ dense, если индекс доступен) — полная гибридная формула §10.2.

``rerank on`` прогоняет тот же MMR-проход (§12.9) над кандидатами ячейки. Вердикт
(§4.11 acceptance): hybrid+rerank ``Recall@10`` / ``MRR`` / ``nDCG@10`` не ниже
каждого одиночного бэкенда (в обоих режимах rerank).

EN: read-only over the store; no writes, no edits to existing modules. New router —
wire via ``routers/__init__.py`` (see feature wiring). Deterministic: same store +
golden → same numbers.
"""

from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/retrieval-eval", tags=["retrieval-eval"])

_K = 10
_CANDIDATE_LIMIT = 200
_MMR_LAMBDA = 0.7
_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_TEXT_FIELDS = ("name", "canonical_name", "aliases_text", "text")

# Catalogue surfaced by GET /retrieval-eval/config (drives the dashboard header).
BACKEND_INFO: dict[str, dict[str, str]] = {
    "bm25": {
        "label": "BM25 / keyword",
        "desc": "Sparse keyword-overlap ranking only (bm25-style single backend).",
    },
    "dense": {
        "label": "Dense / vector",
        "desc": "Entity vector index (semantic); degrades to keyword if the index is empty.",
    },
    "hybrid": {
        "label": "Hybrid (fusion)",
        "desc": "weighted_fuse(keyword + evidence_quality + graph_proximity[+dense]) — §10.2.",
    },
}
_BACKENDS = ("bm25", "dense", "hybrid")
_SINGLE_BACKENDS = ("bm25", "dense")

METRIC_INFO: tuple[dict[str, Any], ...] = (
    {"id": "recall_at_10", "label": "Recall@10", "higher_is_better": True},
    {"id": "mrr", "label": "MRR", "higher_is_better": True},
    {"id": "ndcg_at_10", "label": "nDCG@10", "higher_is_better": True},
    {"id": "precision_at_10", "label": "Precision@10", "higher_is_better": True},
    {"id": "hit_at_10", "label": "hit@10", "higher_is_better": True},
)
# Metrics that decide the §4.11 acceptance verdict (hybrid+rerank must win these).
_VERDICT_METRICS = ("recall_at_10", "mrr", "ndcg_at_10")


# --------------------------------------------------------------------------- #
# Live candidate retrieval (parameterized keyword-contains, read-only Cypher)  #
# --------------------------------------------------------------------------- #
def _tokenize(text: str | None) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def _keyword_score(node: dict[str, Any], tokens: set[str]) -> float:
    """Exact query-token overlap over the node's text fields, normalised to [0, 1]."""
    hay = _tokenize(" ".join(str(node.get(f) or "") for f in _TEXT_FIELDS))
    return len(tokens & hay) / (len(tokens) or 1)


def _text_of(node: dict[str, Any]) -> str:
    for f in ("text", "name", "canonical_name"):
        v = node.get(f)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _candidate_nodes(store: Any, query: str, limit: int = _CANDIDATE_LIMIT) -> dict[str, dict]:
    """Nodes whose text columns CONTAIN any query token (parameterized Cypher)."""
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


def _nodes_by_ids(store: Any, ids: list[str]) -> dict[str, dict]:
    """Fetch node dicts for explicit ids (used for dense hits outside the keyword set)."""
    if not ids:
        return {}
    out: dict[str, dict] = {}
    try:
        rows = store.rows("MATCH (n:Node) WHERE n.id IN $ids RETURN n", {"ids": ids})
        for row in rows:
            nd = store._node_dict(row[0])
            nid = nd.get("id")
            if nid:
                out[str(nid)] = nd
    except Exception:
        return {}
    return out


# --------------------------------------------------------------------------- #
# Backends (each returns (id, relevance) descending) over one query's nodes    #
# --------------------------------------------------------------------------- #
def _scored_bm25(nodes: dict[str, dict], tokens: set[str]) -> list[tuple[str, float]]:
    scored = [(nid, _keyword_score(nd, tokens)) for nid, nd in nodes.items()]
    scored = [(i, s) for i, s in scored if s > 0]
    scored.sort(key=lambda p: (-p[1], p[0]))
    return scored


def _dense_hits(query: str) -> list[tuple[str, float]] | None:
    """Entity vector index hits (id, score) or ``None`` when the index is empty/absent."""
    try:
        from kg_retrievers.entity_index import EntityVectorIndex

        idx = EntityVectorIndex()
        if idx.count() <= 0:
            return None
        hits = idx.similar_entities(query, k=_CANDIDATE_LIMIT)
        ranked = [(str(h.id), float(h.score)) for h in hits]
        return ranked or None
    except Exception:
        return None


def _scored_dense(
    store: Any, query: str, nodes: dict[str, dict], tokens: set[str]
) -> tuple[list[tuple[str, float]], dict[str, dict], bool]:
    """Dense ranking + node lookup for rerank text; degrades to keyword if no index.

    Returns ``(scored, node_lookup, degraded)`` where ``degraded`` is True when the
    vector index was unavailable and we fell back to keyword order (honest reporting).
    """
    hits = _dense_hits(query)
    if hits is None:
        return _scored_bm25(nodes, tokens), nodes, True
    lookup = dict(nodes)
    missing = [nid for nid, _ in hits if nid not in lookup]
    lookup.update(_nodes_by_ids(store, missing))
    return hits, lookup, False


def _scored_hybrid(store: Any, nodes: dict[str, dict], tokens: set[str]) -> list[tuple[str, float]]:
    """Full §10.2 fusion: keyword + evidence_quality + graph_proximity over candidates."""
    from kg_retrievers.scoring import evidence_quality_score, graph_proximity_score, weighted_fuse

    kw = {nid: s for nid, nd in nodes.items() if (s := _keyword_score(nd, tokens)) > 0}
    if not kw:
        return []
    seeds = [nid for nid, _ in sorted(kw.items(), key=lambda p: (-p[1], p[0]))[:3]]
    comps: dict[str, dict[str, float]] = {
        "keyword": kw,
        "evidence_quality": {nid: evidence_quality_score(nodes[nid]) for nid in kw},
        "graph_proximity": {nid: graph_proximity_score(store, nid, seeds) for nid in kw},
    }
    fused = weighted_fuse(comps)
    return [(f.id, f.score) for f in fused]


# --------------------------------------------------------------------------- #
# §12.9 MMR rerank pass over a cell's candidate order                          #
# --------------------------------------------------------------------------- #
def _rerank(scored: list[tuple[str, float]], lookup: dict[str, dict]) -> list[str]:
    """Reorder candidates by MMR (§12.9) using their relevance + text; ids preserved."""
    from kg_retrievers.rerank import mmr_rerank

    if not scored:
        return []
    cands = [
        {"id": nid, "score": s, "text": _text_of(lookup.get(nid, {}))} for nid, s in scored
    ]
    return [item.id for item in mmr_rerank(cands, lambda_=_MMR_LAMBDA)]


# --------------------------------------------------------------------------- #
# Matrix run                                                                   #
# --------------------------------------------------------------------------- #
class RunRequest(BaseModel):
    rerank: bool = Field(default=True, description="Also compute the rerank-on column")


def _cell_metrics(runs: list[tuple[list[str], set[str]]]) -> dict[str, float]:
    """Macro-averaged Recall@10/MRR/nDCG@10/Precision@10/hit@10 for one cell (§18.6)."""
    from kg_eval.retrieval_metrics import aggregate

    agg = aggregate(runs, _K)
    return {
        "recall_at_10": round(agg.recall_at_k, 6),
        "mrr": round(agg.mrr, 6),
        "ndcg_at_10": round(agg.ndcg_at_k, 6),
        "precision_at_10": round(agg.precision_at_k, 6),
        "hit_at_10": round(agg.hit_at_k, 6),
    }


def _rank_cell(
    store: Any,
    backend: str,
    query: str,
    nodes: dict[str, dict],
    tokens: set[str],
) -> tuple[list[str], list[str], bool]:
    """Return (base ranked ids, reranked ids, degraded) for one backend on one query."""
    degraded = False
    if backend == "bm25":
        scored = _scored_bm25(nodes, tokens)
        lookup = nodes
    elif backend == "dense":
        scored, lookup, degraded = _scored_dense(store, query, nodes, tokens)
    else:  # hybrid
        scored = _scored_hybrid(store, nodes, tokens)
        lookup = nodes
    base_ids = [nid for nid, _ in scored]
    reranked_ids = _rerank(scored, lookup)
    return base_ids, reranked_ids, degraded


def _verdict(cells: dict[tuple[str, bool], dict[str, float]], want_rerank: bool) -> dict[str, Any]:
    """hybrid+rerank vs every single backend (both rerank modes) on §4.11 metrics."""
    champion_key = ("hybrid", want_rerank)
    champion = cells[champion_key]
    modes = (False, True) if want_rerank else (False,)
    per_metric: list[dict[str, Any]] = []
    all_win = True
    for metric in _VERDICT_METRICS:
        best_single = 0.0
        best_single_from = ""
        for backend in _SINGLE_BACKENDS:
            for mode in modes:
                val = cells[(backend, mode)][metric]
                if val > best_single:
                    best_single = val
                    best_single_from = f"{backend}{'+rerank' if mode else ''}"
        champ_val = champion[metric]
        wins = champ_val >= best_single - 1e-9
        all_win = all_win and wins
        per_metric.append(
            {
                "metric": metric,
                "champion": round(champ_val, 6),
                "best_single": round(best_single, 6),
                "best_single_from": best_single_from,
                "delta": round(champ_val - best_single, 6),
                "wins": wins,
            }
        )
    return {
        "champion": "hybrid+rerank" if want_rerank else "hybrid",
        "passes": all_win,
        "per_metric": per_metric,
    }


@router.get("/config")
def retrieval_eval_config() -> dict[str, Any]:
    """List backends, metrics, golden queries and dense-index availability (§4.11)."""
    from kg_eval.retrieval_eval import GOLDEN

    dense_ready = False
    try:
        from kg_retrievers.entity_index import EntityVectorIndex

        dense_ready = EntityVectorIndex().count() > 0
    except Exception:
        dense_ready = False
    return {
        "k": _K,
        "backends": [{"id": b, **BACKEND_INFO[b]} for b in _BACKENDS],
        "metrics": list(METRIC_INFO),
        "verdict_metrics": list(_VERDICT_METRICS),
        "golden": [
            {"query": q, "relevant_ids": list(rel), "n_relevant": len(rel)} for q, rel in GOLDEN
        ],
        "golden_size": len(GOLDEN),
        "dense_index_ready": dense_ready,
        "mmr_lambda": _MMR_LAMBDA,
    }


@router.post("/run")
def retrieval_eval_run(req: RunRequest, role: str = Depends(current_role)) -> dict[str, Any]:
    """Run the backend × rerank matrix over the golden set → metrics + verdict (§4.11).

    Для каждой ячейки (bm25/dense/hybrid × rerank off/on) считает макро-усреднённые
    Recall@10 / MRR / nDCG@10 / Precision@10 / hit@10 над живым графом и выносит
    вердикт: побеждает ли hybrid+rerank каждый одиночный бэкенд.
    """
    from kg_eval.retrieval_eval import GOLDEN

    store = get_store()
    golden = [(q, set(rel)) for q, rel in GOLDEN]

    # Pre-fetch candidate nodes + tokens once per query (shared across all backends).
    per_query_nodes = {q: _candidate_nodes(store, q) for q, _ in golden}
    per_query_tokens = {q: _tokenize(q) for q, _ in golden}

    modes = [False, True] if req.rerank else [False]
    # runs[(backend, rerank)] = list of (ranked_ids, relevant_set) over the golden set.
    runs: dict[tuple[str, bool], list[tuple[list[str], set[str]]]] = {
        (b, m): [] for b in _BACKENDS for m in modes
    }
    dense_degraded = False

    t0 = time.perf_counter()
    for query, relevant in golden:
        nodes = per_query_nodes[query]
        tokens = per_query_tokens[query]
        for backend in _BACKENDS:
            base_ids, reranked_ids, degraded = _rank_cell(store, backend, query, nodes, tokens)
            if backend == "dense" and degraded:
                dense_degraded = True
            runs[(backend, False)].append((base_ids, relevant))
            if req.rerank:
                runs[(backend, True)].append((reranked_ids, relevant))
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    cells = {key: _cell_metrics(pairs) for key, pairs in runs.items()}

    # Flat matrix for the UI: one row per (backend, rerank) with all metrics.
    matrix = [
        {
            "backend": backend,
            "backend_label": BACKEND_INFO[backend]["label"],
            "rerank": mode,
            "metrics": cells[(backend, mode)],
        }
        for backend in _BACKENDS
        for mode in modes
    ]

    verdict = _verdict(cells, want_rerank=req.rerank)
    return {
        "k": _K,
        "golden_size": len(golden),
        "backends": [{"id": b, **BACKEND_INFO[b]} for b in _BACKENDS],
        "metrics": list(METRIC_INFO),
        "rerank_evaluated": req.rerank,
        "matrix": matrix,
        "verdict": verdict,
        "dense_degraded_to_keyword": dense_degraded,
        "elapsed_ms": elapsed_ms,
    }
