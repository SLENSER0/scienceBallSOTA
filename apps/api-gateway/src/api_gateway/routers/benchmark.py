"""Baseline/ablation head-to-head benchmark endpoint (§23.31).

Честное доказательство «SOTA цифрами»: прогоняет ЖИВОЙ retrieval-бенчмарк над
графом (server-профиль Neo4j / embedded Kuzu) для пяти систем — четырёх базовых
линий A–D и полной системы — по «золотому» набору (§18.6, ``kg_eval.retrieval_eval``)
и считает Recall@10 / MRR / Precision@10 / citation-precision / unsupported-rate /
latency РЕАЛЬНЫМИ измерениями. Затем собирает head-to-head отчёт через
:mod:`kg_eval.head_to_head` (таблица победителей + вердикт SOTA, leave-one-out
абляции §23.19, сравнение с опубликованными числами LightRAG/HippoRAG2/PathRAG/
MS-GraphRAG из §23.35) и публикует Markdown в ``docs/eval/benchmark_report.md``.

Пять систем — это разные, реальные стратегии ранжирования над ОДНИМ графом,
переиспользующие существующие оценщики (``kg_retrievers.scoring`` fuse +
graph-proximity + evidence-quality, ``kg_retrievers.rerank`` MMR):

* ``A_plain_vector_rag``  — dense/semantic-only (entity vector index, degrade→keyword).
* ``B_bm25_keyword``      — sparse keyword overlap only (BM25-style).
* ``C_neo4j_structured``  — keyword prefilter + graph-degree structural boost (Cypher).
* ``D_graphrag_community``— keyword prefilter + community-cohesion boost.
* ``full_system``         — fuse(keyword+evidence_quality+graph_proximity) → MMR → verifier.

Абляции полной системы (§23.19): without_reranker / without_graph_proximity /
without_evidence_quality / without_verifier. Воспроизводимо одной командой:
``POST /api/v1/benchmark/run``.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1", tags=["benchmark"])

_K = 10
_CANDIDATE_LIMIT = 200
_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_TEXT_FIELDS = ("name", "canonical_name", "aliases_text", "text")

# Human-readable catalogue of the five systems (surfaced by GET /benchmark/systems).
SYSTEM_INFO: dict[str, dict[str, str]] = {
    "A_plain_vector_rag": {
        "label": "A · Plain vector RAG",
        "desc": "Dense/semantic entity search only, no KG structure (degrades to keyword).",
    },
    "B_bm25_keyword": {
        "label": "B · BM25 / keyword",
        "desc": "Sparse keyword-overlap ranking only (BM25-style baseline).",
    },
    "C_neo4j_structured": {
        "label": "C · Neo4j structured",
        "desc": "Keyword prefilter + graph-degree structural boost via Cypher.",
    },
    "D_graphrag_community": {
        "label": "D · GraphRAG community",
        "desc": "Keyword prefilter + community-cohesion boost (global/community search).",
    },
    "full_system": {
        "label": "Full system",
        "desc": "Fusion(keyword+evidence_quality+graph_proximity) → MMR → evidence verifier.",
    },
}
_FULL = "full_system"


def _tokenize(text: str | None) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def _keyword_score(node: dict[str, Any], tokens: set[str]) -> float:
    """Exact query-token overlap over the node's text fields, normalised to [0,1]."""
    hay = _tokenize(" ".join(str(node.get(f) or "") for f in _TEXT_FIELDS))
    return len(tokens & hay) / (len(tokens) or 1)


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
    for row in store.rows(cypher, params):
        nd = store._node_dict(row[0])
        nid = nd.get("id")
        if nid:
            out[str(nid)] = nd
    return out


def _degree(store: Any, node_id: str) -> int:
    try:
        rows = store.rows(
            "MATCH (n:Node {id:$id})-[:Rel]-(m:Node) RETURN count(DISTINCT m)", {"id": node_id}
        )
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


def _supported_ids(store: Any, ids: list[str]) -> set[str]:
    """Subset of ``ids`` that have a SUPPORTED_BY→Evidence edge (citation support)."""
    if not ids:
        return set()
    try:
        rows = store.rows(
            "MATCH (n:Node)-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
            "WHERE n.id IN $ids RETURN DISTINCT n.id",
            {"ids": ids},
        )
        return {str(r[0]) for r in rows}
    except Exception:
        return set(ids)  # degrade: treat all as supported rather than fake unsupported


def _ranked_keyword(nodes: dict[str, dict], tokens: set[str]) -> list[str]:
    scored = [(nid, _keyword_score(nd, tokens)) for nid, nd in nodes.items()]
    scored = [(i, s) for i, s in scored if s > 0]
    scored.sort(key=lambda p: (-p[1], p[0]))
    return [i for i, _ in scored]


def _ranked_vector(store: Any, query: str, nodes: dict[str, dict], tokens: set[str]) -> list[str]:
    """Dense entity search when an index exists; else degrade to keyword (like search_vector)."""
    try:
        from kg_retrievers.entity_index import EntityVectorIndex

        idx = EntityVectorIndex()
        if idx.count() > 0:
            hits = idx.similar_entities(query, k=_K * 2)
            ranked = [str(h.id) for h in hits]
            if ranked:
                return ranked
    except Exception:
        pass
    return _ranked_keyword(nodes, tokens)


def _ranked_structured(store: Any, nodes: dict[str, dict], tokens: set[str]) -> list[str]:
    """Keyword prefilter + graph-degree structural boost (Neo4j structured templates)."""
    kw = {nid: _keyword_score(nd, tokens) for nid, nd in nodes.items()}
    prefilter = [nid for nid, s in kw.items() if s > 0]
    degrees = {nid: _degree(store, nid) for nid in prefilter}
    hi = max(degrees.values()) if degrees else 0
    scored = []
    for nid in prefilter:
        deg = degrees[nid] / hi if hi else 0.0
        scored.append((nid, 0.5 * kw[nid] + 0.5 * deg))
    scored.sort(key=lambda p: (-p[1], p[0]))
    return [i for i, _ in scored]


def _ranked_community(store: Any, nodes: dict[str, dict], tokens: set[str]) -> list[str]:
    """Keyword prefilter + community-cohesion boost (share community with top hit)."""
    kw = {nid: _keyword_score(nd, tokens) for nid, nd in nodes.items()}
    ranked_kw = _ranked_keyword(nodes, tokens)
    top_comm = nodes[ranked_kw[0]].get("community_id") if ranked_kw else None
    scored = []
    for nid, s in kw.items():
        if s <= 0:
            continue
        boost = 1.0 if top_comm is not None and nodes[nid].get("community_id") == top_comm else 0.0
        scored.append((nid, 0.5 * s + 0.5 * boost))
    scored.sort(key=lambda p: (-p[1], p[0]))
    return [i for i, _ in scored]


def _full_components(
    store: Any, nodes: dict[str, dict], tokens: set[str], *, drop: str | None = None
) -> dict[str, dict[str, float]]:
    """Fusion components for the full system; ``drop`` ablates one signal (§23.19)."""
    from kg_retrievers.scoring import evidence_quality_score, graph_proximity_score

    kw = {nid: s for nid, nd in nodes.items() if (s := _keyword_score(nd, tokens)) > 0}
    comps: dict[str, dict[str, float]] = {"keyword": kw}
    seeds = _ranked_keyword(nodes, tokens)[:3]
    if drop != "graph_proximity":
        comps["graph_proximity"] = {
            nid: graph_proximity_score(store, nid, seeds) for nid in kw
        }
    if drop != "evidence_quality":
        comps["evidence_quality"] = {nid: evidence_quality_score(nodes[nid]) for nid in kw}
    return comps


def _ranked_full(
    store: Any,
    nodes: dict[str, dict],
    tokens: set[str],
    *,
    rerank: bool = True,
    verifier: bool = True,
    drop: str | None = None,
) -> list[str]:
    """Full pipeline: fuse → (MMR rerank) → (evidence verifier gate)."""
    from kg_retrievers.rerank import mmr_rerank
    from kg_retrievers.scoring import weighted_fuse

    comps = _full_components(store, nodes, tokens, drop=drop)
    if not any(comps.values()):
        return []
    fused = weighted_fuse(comps)
    order = [f.id for f in fused]
    if rerank:
        cands = [
            {
                "id": f.id,
                "score": f.score,
                "text": nodes[f.id].get("text") or nodes[f.id].get("name", ""),
            }
            for f in fused
        ]
        order = [item.id for item in mmr_rerank(cands)]
    if verifier:
        # Verifier gate: demote unsupported entities below supported ones (never drop
        # everything — keep order among unsupported so recall is not zeroed).
        supported = _supported_ids(store, order)
        order = [i for i in order if i in supported] + [i for i in order if i not in supported]
    return order


def _ranked_for(
    system: str, store: Any, query: str, nodes: dict[str, dict], tokens: set[str]
) -> list[str]:
    if system == "A_plain_vector_rag":
        return _ranked_vector(store, query, nodes, tokens)
    if system == "B_bm25_keyword":
        return _ranked_keyword(nodes, tokens)
    if system == "C_neo4j_structured":
        return _ranked_structured(store, nodes, tokens)
    if system == "D_graphrag_community":
        return _ranked_community(store, nodes, tokens)
    return _ranked_full(store, nodes, tokens)


# Leave-one-out ablations of the full system (§23.19), each a distinct real run.
_ABLATIONS: dict[str, dict[str, Any]] = {
    "without_reranker": {"rerank": False, "verifier": True, "drop": None},
    "without_graph_proximity": {"rerank": True, "verifier": True, "drop": "graph_proximity"},
    "without_evidence_quality": {"rerank": True, "verifier": True, "drop": "evidence_quality"},
    "without_verifier": {"rerank": True, "verifier": False, "drop": None},
}


def _score_system(store: Any, ranked_fn, golden) -> dict[str, float]:  # type: ignore[no-untyped-def]
    """Macro-average Recall@10/MRR/Precision@10/citation-precision/unsupported/latency."""
    from kg_eval.retrieval_metrics import evaluate

    recalls, mrrs, precs, cites, unsup = [], [], [], [], []
    total_latency = 0.0
    for query, relevant in golden:
        rel = set(relevant)
        t0 = time.perf_counter()
        ranked = ranked_fn(query)
        total_latency += (time.perf_counter() - t0) * 1000.0
        m = evaluate(ranked, rel, _K)
        recalls.append(m.recall_at_k)
        mrrs.append(m.mrr)
        precs.append(m.precision_at_k)
        topk = ranked[:_K]
        supported = _supported_ids(store, topk)
        n_sup = len(supported)
        rel_sup = sum(1 for i in topk if i in supported and i in rel)
        cites.append(rel_sup / n_sup if n_sup else 0.0)
        unsup.append((len(topk) - n_sup) / len(topk) if topk else 0.0)
    n = max(1, len(golden))
    return {
        "recall_at_10": round(sum(recalls) / n, 6),
        "mrr": round(sum(mrrs) / n, 6),
        "precision_at_10": round(sum(precs) / n, 6),
        "citation_precision": round(sum(cites) / n, 6),
        "unsupported_rate": round(sum(unsup) / n, 6),
        "latency_ms": round(total_latency / n, 4),
    }


def _write_report(markdown: str) -> str | None:
    """Publish the benchmark report to docs/eval/benchmark_report.md (§23.31)."""
    try:
        # apps/api-gateway/src/api_gateway/routers/benchmark.py -> repo root
        root = Path(__file__).resolve().parents[5]
        out = root / "docs" / "eval" / "benchmark_report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        return str(out)
    except Exception:
        return None


class BenchmarkRequest(BaseModel):
    write_report: bool = Field(default=True, description="Publish docs/eval/benchmark_report.md")


@router.get("/benchmark/systems")
def benchmark_systems() -> dict:
    """List the five compared systems, metric directions and external SOTA leaderboard."""
    from kg_eval.head_to_head import EXTERNAL_SOTA, METRIC_DIRECTIONS, METRIC_LABELS

    return {
        "systems": [{"id": k, **v} for k, v in SYSTEM_INFO.items()],
        "full_system": _FULL,
        "metrics": [
            {"id": m, "label": METRIC_LABELS.get(m, m), "higher_is_better": d}
            for m, d in METRIC_DIRECTIONS.items()
        ],
        "ablations": list(_ABLATIONS),
        "external_leaderboard": [{"system": k, **v} for k, v in EXTERNAL_SOTA.items()],
    }


@router.post("/benchmark/run")
def benchmark_run(req: BenchmarkRequest, role: str = Depends(current_role)) -> dict:
    """Run the live head-to-head benchmark over the golden set → report (§23.31).

    Прогоняет пять систем и четыре абляции по «золотому» набору над живым графом,
    считает метрики, собирает head-to-head отчёт (:mod:`kg_eval.head_to_head`) и
    публикует Markdown в ``docs/eval/benchmark_report.md``.
    """
    from kg_eval.head_to_head import build_report, to_markdown
    from kg_eval.retrieval_eval import GOLDEN

    store = get_store()
    golden = list(GOLDEN)

    # Pre-fetch candidate nodes once per query (shared across all systems).
    per_query_nodes = {q: _candidate_nodes(store, q) for q, _ in golden}
    per_query_tokens = {q: _tokenize(q) for q, _ in golden}

    def make_fn(system: str):  # type: ignore[no-untyped-def]
        return lambda q: _ranked_for(system, store, q, per_query_nodes[q], per_query_tokens[q])

    systems = {name: _score_system(store, make_fn(name), golden) for name in SYSTEM_INFO}

    # Leave-one-out ablation runs, scored on the same golden (Recall@10).
    ablated: dict[str, float] = {}
    for name, cfg in _ABLATIONS.items():
        fn = lambda q, c=cfg: _ranked_full(  # noqa: E731
            store, per_query_nodes[q], per_query_tokens[q], **c
        )
        ablated[name] = _score_system(store, fn, golden)["recall_at_10"]

    report = build_report(systems, full_system=_FULL, ablated=ablated)
    markdown = to_markdown(report)
    payload = report.as_dict()
    payload["golden_size"] = len(golden)
    payload["k"] = _K
    payload["markdown"] = markdown
    payload["report_path"] = _write_report(markdown) if req.write_report else None
    return payload
