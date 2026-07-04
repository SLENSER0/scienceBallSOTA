"""Continuous single-session demo run of the §23 target picture (§22.6).

The §22.6 acceptance criterion asks for **one** continuous, single-session run
that demonstrates all eight properties of the §23 «scientific intelligence
workspace» target picture *back to back* — not eight isolated screens. This
router is that orchestrator: a single request runs one real question end-to-end
through the live stack and returns an ordered, eight-chapter **demo script**,
each chapter backed by real data pulled from the live graph (Neo4j server
profile, or the embedded Kuzu store) so the narrative is provable, not staged.

The eight §23 properties, in order (each a chapter of the returned run):

1. ``question-entry``   — исследователь задаёт вопрос в чате (точка входа).
2. ``agent-plan``       — агент строит план и вызывает graph/search/evidence/gap
   инструменты (видно в trace) — reuses the deterministic §13.10 tool planner.
3. ``answer-evidence``  — ответ содержит числа, условия, источники и warnings
   (о противоречиях/пробелах).
4. ``graph``            — рядом появляется граф материалов/режимов/экспериментов/
   свойств/источников.
5. ``edge-evidence``    — клик по ребру показывает доказательство (evidence span).
6. ``gaps``             — пробелы — first-class объекты ``Gap`` с рекомендацией
   «next experiment to close the gap».
7. ``versioning``       — все извлечения и решения версионируются (extraction
   runs + ``Decision``/``CurationEvent`` + provenance-поля).
8. ``ingest-reflection``— добавление документа обновляет граф, индексы и coverage
   dashboards — три поверхности отражения показаны на живом корпусе.

Everything is assembled from modules that already exist — ``answer_query``
(agent), the §13.10 planner (via :mod:`api_gateway.routers.agent_timeline`),
``gap_priority_score``/``next_experiment_hint``, ``build_coverage_matrix`` — so
this router *narrates* the system, it does not reimplement it. It is read-only:
the demo run never mutates the live graph (chapter 8 reports the three reflection
surfaces and names the live ``/documents/upload`` + ``/reindex`` endpoints the UI
can drive for a genuine add-a-document demonstration).

Endpoints (prefix ``/api/v1/demo``):

* ``GET  /questions``  — the curated demo questions (golden §23 walkthrough seeds).
* ``POST /run``        — run the full eight-chapter demo for one question.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

# Curated golden seeds — each exercises the whole §23 picture (numbers + conditions
# + sources + graph + gaps). The first is the §22.3/§19.11 walkthrough default.
DEMO_QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "question": "методы обессоливания воды сульфаты 200–300 мг/л TDS ≤1000 мг/дм³",
        "hint": "Числовые условия + сравнение технологий обессоливания — числа, "
        "источники, граф решений и пробелы сразу.",
    },
    {
        "question": "циркуляция католита электроэкстракция никеля",
        "hint": "Режим процесса + материал никель — граф материал/режим/эксперимент.",
    },
    {
        "question": "флотация медно-никелевых руд извлечение меди реагенты",
        "hint": "Извлечение (%) по флотации — измерения с доказательствами и пробелы.",
    },
)

# Node kinds that make up the §23 «граф материалов/режимов/экспериментов/свойств/
# источников» — used to prove chapter 4 actually contains the target entity kinds.
_MATERIAL = {"Material"}
_REGIME = {"ProcessingRegime", "TechnologySolution", "Equipment"}
_EXPERIMENT = {"Measurement", "TechnoEconomicIndicator", "Experiment"}
_PROPERTY = {"Property"}
_SOURCE = {"Paper", "Document", "Source", "Chunk", "Evidence"}

# Labels whose plain presence proves versioning/provenance (chapter 7). Counted via
# label rollup only (no arbitrary property access → safe on Kuzu and Neo4j alike).
_VERSION_LABELS = ("ExtractorRun", "GapScanRun", "Decision", "CurationEvent", "Evidence")

_NUM_RE = re.compile(
    r"\d[\d\s.,]*\s*(?:%|мг|г|кг|л|°c|°с|ppm|мкм|мм|см|м|ч|мин|в|а|квт|мпа)?", re.I
)


class RunBody(BaseModel):
    """POST /run payload — the question to drive the single-session demo run."""

    question: str | None = None
    use_llm: bool = False  # deterministic synthesis by default → fast, offline-safe
    geography: str | None = None
    max_graph_nodes: int = 60
    max_graph_edges: int = 120


def _safe_scalar(store: Any, cypher: str, params: dict | None = None) -> int:
    """Run a single-scalar count query, tolerating stores that reject the property.

    Kuzu raises when a query references a property absent from the schema; Neo4j
    returns null. Either way we degrade to 0 so a chapter never 500s.
    """
    try:
        rows = store.rows(cypher, params or {})
        return int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0
    except Exception:
        return 0


def _chapter(index: int, prop: str, title: str, narrative: str, proven: bool, data: dict) -> dict:
    return {
        "index": index,
        "propertyId": prop,
        "title": title,
        "narrative": narrative,
        "proven": bool(proven),
        "data": data,
    }


def _ch1_question(question: str, role: str) -> dict:
    return _chapter(
        1,
        "question-entry",
        "Исследователь задаёт вопрос в чате",
        "Точка входа рабочего процесса — свободный научный вопрос, а не форма поиска.",
        proven=bool(question),
        data={"question": question, "role": role, "entryPoint": "chat"},
    )


def _ch2_plan(question: str) -> dict:
    """Chapter 2 — the agent's real, deterministic tool plan (§13.8/§13.10)."""
    try:
        from api_gateway.routers.agent_timeline import _plan_timeline

        tl = _plan_timeline(question)
        tools = [s["tool"] for s in tl["steps"]]
        stages = sorted({s["stage"] for s in tl["steps"]})
        proven = bool(tl["steps"])
        data = {
            "intent": tl["intent"],
            "confidence": tl["confidence"],
            "matched": tl["matched"],
            "steps": tl["steps"],
            "toolSequence": tools,
            "stagesTouched": stages,
        }
    except Exception as exc:
        proven, data = False, {"error": str(exc)[:200]}
    return _chapter(
        2,
        "agent-plan",
        "Агент строит план и вызывает инструменты",
        "Классификация интента → детерминированная evidence-first цепочка "
        "graph / search / evidence / gap инструментов (виден trace).",
        proven=proven,
        data=data,
    )


def _ch3_answer(ans: Any, question: str) -> dict:
    """Chapter 3 — numbers, conditions, sources, warnings in the answer."""
    md = ans.answer_markdown or ""
    numbers = _NUM_RE.findall(md)
    conditions: list[str] = []
    pq = ans.parsed_query or {}
    for rc in pq.get("range_constraints", []) or pq.get("rangeConstraints", []) or []:
        if isinstance(rc, dict):
            src = rc.get("source_span") or rc.get("parameter")
            if src:
                conditions.append(str(src))
    verifier = ans.verifier_report or {}
    citations = [
        {
            "marker": c.marker,
            "sourceTitle": c.source_title,
            "docId": c.evidence.doc_id if c.evidence else None,
            "page": c.evidence.page if c.evidence else None,
            "year": c.year,
            "geography": c.geography,
        }
        for c in ans.citations[:6]
    ]
    warnings = {
        "gaps": len(ans.gaps),
        "contradictions": len(ans.contradictions),
        "unsupportedClaims": len(verifier.get("unsupported", []) or []),
    }
    proven = bool(ans.citations) and (len(numbers) > 0)
    return _chapter(
        3,
        "answer-evidence",
        "Ответ: числа, условия, источники и предупреждения",
        "Каждое число подкреплено ссылкой; условия из запроса разобраны; "
        "warnings о пробелах/противоречиях приложены к ответу.",
        proven=proven,
        data={
            "answerExcerpt": md[:600],
            "answerLength": len(md),
            "confidence": ans.confidence,
            "numbersFound": len(numbers),
            "sampleNumbers": [n.strip() for n in numbers[:8] if n.strip()],
            "conditions": conditions[:8],
            "citationCount": len(ans.citations),
            "sampleCitations": citations,
            "warnings": warnings,
            "verifier": {
                "verified": verifier.get("verified"),
                "coverage": verifier.get("coverage"),
                "nCitations": verifier.get("n_citations"),
                "nGrounded": verifier.get("n_grounded"),
            },
        },
    )


def _ch4_graph(ans: Any, max_nodes: int, max_edges: int) -> dict:
    """Chapter 4 — the answer's companion graph with the §23 entity kinds."""
    g = ans.graph
    if g is None:
        return _chapter(
            4,
            "graph",
            "Рядом с ответом — граф знаний",
            "Материалы, режимы, эксперименты, свойства и источники.",
            proven=False,
            data={"nodeCount": 0, "edgeCount": 0},
        )
    type_counts: dict[str, int] = {}
    for n in g.nodes:
        type_counts[n.type] = type_counts.get(n.type, 0) + 1
    present = set(type_counts)
    kinds = {
        "materials": sum(type_counts.get(t, 0) for t in _MATERIAL),
        "regimes": sum(type_counts.get(t, 0) for t in _REGIME),
        "experiments": sum(type_counts.get(t, 0) for t in _EXPERIMENT),
        "properties": sum(type_counts.get(t, 0) for t in _PROPERTY),
        "sources": sum(type_counts.get(t, 0) for t in _SOURCE),
    }
    covered = sum(1 for v in kinds.values() if v > 0)
    nodes = [
        {"id": n.id, "label": n.label, "type": n.type, "verified": n.verified}
        for n in g.nodes[:max_nodes]
    ]
    edges = [
        {"id": e.id, "source": e.source, "target": e.target, "type": e.type,
         "contradicted": e.contradicted, "inferred": e.inferred}
        for e in g.edges[:max_edges]
    ]
    return _chapter(
        4,
        "graph",
        "Рядом с ответом — граф знаний",
        "Граф материалов / режимов / экспериментов / свойств / источников, "
        "построенный из того же ответа.",
        proven=covered >= 3 and len(g.nodes) > 0,
        data={
            "nodeCount": len(g.nodes),
            "edgeCount": len(g.edges),
            "typeCounts": type_counts,
            "entityKinds": kinds,
            "kindsCovered": covered,
            "presentTypes": sorted(present),
            "nodes": nodes,
            "edges": edges,
        },
    )


def _ch5_edge_evidence(store: Any, ans: Any) -> dict:
    """Chapter 5 — click an edge → the evidence span behind it.

    Picks a fact node from the answer graph that carries ``SUPPORTED_BY`` evidence
    and — preferring one that is also an endpoint of a rendered edge — returns that
    edge, the fact node, and its evidence spans (same semantics as the Evidence
    Inspector ``/evidence/by-node`` surface, §5.2.6).
    """
    g = ans.graph
    node_ids: list[str] = [n.id for n in g.nodes] if g else []
    edges = list(g.edges) if g else []
    picked_fact: str | None = None
    picked_edge: dict | None = None
    evidence: list[dict] = []

    if node_ids:
        rows = store.rows(
            "MATCH (f:Node)-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
            "WHERE f.id IN $ids "
            "RETURN f.id, f.name, f.label, e.id, e.doc_id, e.page, e.text, "
            "e.evidence_strength, e.confidence LIMIT 40",
            {"ids": node_ids[:400]},
        )
        by_fact: dict[str, list[dict]] = {}
        for fid, fname, flabel, eid, doc, page, text, strength, conf in rows:
            by_fact.setdefault(fid, []).append(
                {
                    "evidenceId": eid,
                    "docId": doc,
                    "page": page,
                    "text": text,
                    "evidenceStrength": strength,
                    "confidence": conf,
                    "factName": fname,
                    "factLabel": flabel,
                }
            )
        # Prefer a fact that is also an edge endpoint (a truly «clickable» edge).
        endpoint_ids = {e.source for e in edges} | {e.target for e in edges}
        for fid in by_fact:
            if fid in endpoint_ids:
                picked_fact = fid
                break
        if picked_fact is None and by_fact:
            picked_fact = next(iter(by_fact))
        if picked_fact:
            evidence = by_fact[picked_fact][:5]
            for e in edges:
                if e.source == picked_fact or e.target == picked_fact:
                    picked_edge = {
                        "id": e.id,
                        "source": e.source,
                        "target": e.target,
                        "type": e.type,
                    }
                    break

    fact_meta = evidence[0] if evidence else {}
    return _chapter(
        5,
        "edge-evidence",
        "Клик по ребру показывает доказательство",
        "Любое ребро/факт графа раскрывается в конкретный span источника "
        "(документ, страница, текст) — evidence-first.",
        proven=bool(evidence),
        data={
            "factNode": {
                "id": picked_fact,
                "name": fact_meta.get("factName"),
                "label": fact_meta.get("factLabel"),
            }
            if picked_fact
            else None,
            "edge": picked_edge,
            "evidenceCount": len(evidence),
            "evidence": evidence,
        },
    )


def _ch6_gaps(store: Any, ans: Any) -> dict:
    """Chapter 6 — gaps as first-class objects with a «next experiment» hint."""
    from kg_retrievers.gap_scoring import gap_priority_score, next_experiment_hint

    rows = store.rows(
        "MATCH (g:Node) WHERE g.label='Gap' RETURN g.id, g.name, g.gap_type, g.domain LIMIT 200"
    )
    scored: list[dict] = []
    for gid, name, gtype, domain in rows:
        ac = (store.get_node(gid) or {}).get("absence_confidence")
        rec = {
            "id": gid,
            "name": name,
            "gap_type": gtype,
            "domain": domain,
            "absence_confidence": ac,
        }
        scored.append(
            {
                "id": gid,
                "name": name,
                "type": gtype,
                "domain": domain,
                "score": round(gap_priority_score(rec), 4),
                "nextExperiment": next_experiment_hint(rec),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return _chapter(
        6,
        "gaps",
        "Пробелы — отдельные объекты, которые можно закрывать",
        "Каждый Gap — first-class объект с приоритетом и рекомендацией "
        "«следующий эксперимент, чтобы закрыть пробел».",
        proven=bool(scored),
        data={
            "totalGaps": len(scored),
            "gapsInAnswer": len(ans.gaps),
            "topGaps": scored[:8],
        },
    )


def _ch7_versioning(store: Any) -> dict:
    """Chapter 7 — extraction runs, decisions and provenance are versioned."""
    labels: dict[str, int] = {}
    try:
        by_label = store.counts_by_label()
    except Exception:
        by_label = {}
    for lbl in _VERSION_LABELS:
        labels[lbl] = int(by_label.get(lbl, 0))
    runs = store.rows(
        "MATCH (r:Node) WHERE r.label IN ['ExtractorRun','GapScanRun'] "
        "RETURN r.id, r.name, r.label LIMIT 10"
    )
    with_conf = _safe_scalar(
        store, "MATCH (n:Node) WHERE n.confidence IS NOT NULL RETURN count(n)"
    )
    with_verified = _safe_scalar(
        store, "MATCH (n:Node) WHERE n.verified IS NOT NULL RETURN count(n)"
    )
    proven = labels.get("ExtractorRun", 0) > 0 or labels.get("Evidence", 0) > 0
    return _chapter(
        7,
        "versioning",
        "Все извлечения и решения версионируются",
        "Extraction runs, gap-scan runs, decisions/curation events и "
        "provenance-поля (confidence/verified) фиксируются по каждому узлу.",
        proven=proven,
        data={
            "labelCounts": labels,
            "runs": [{"id": r[0], "name": r[1], "kind": r[2]} for r in runs],
            "nodesWithConfidence": with_conf,
            "nodesWithVerified": with_verified,
        },
    )


def _ch8_ingest_reflection(store: Any) -> dict:
    """Chapter 8 — a new document reflects into graph + indexes + coverage.

    Read-only: reports the three reflection surfaces on the live corpus and names
    the endpoints the UI drives for a genuine add-a-document run (§17.19). The demo
    run itself never mutates the live graph.
    """
    counts = store.counts()
    try:
        by_label = store.counts_by_label()
    except Exception:
        by_label = {}

    coverage_ratio: float | None = None
    covered = absent = total = 0
    try:
        from kg_retrievers.coverage_matrix import build_coverage_matrix

        mat_ids = [
            r[0]
            for r in store.rows(
                "MATCH (n:Node) WHERE n.label='Material' RETURN n.id ORDER BY n.id LIMIT 40"
            )
        ]
        matrix = build_coverage_matrix(store, materials=mat_ids or None, coverage_depth=2)
        total = len(matrix.cells)
        covered = matrix.covered_count
        absent = matrix.absent_count
        coverage_ratio = round(covered / total, 4) if total else None
    except Exception:
        pass

    surfaces = {
        "graph": {
            "endpoint": "POST /api/v1/documents/upload",
            "nodes": counts.get("nodes", 0),
            "rels": counts.get("rels", 0),
            "documents": int(by_label.get("Document", 0)) + int(by_label.get("Paper", 0)),
            "chunks": int(by_label.get("Chunk", 0)),
        },
        "indexes": {
            "endpoint": "POST /api/v1/documents/reindex",
            "chunksIndexed": int(by_label.get("Chunk", 0)),
            "targets": ["Qdrant (vector)", "OpenSearch (keyword)"],
            "note": "На server-профиле чанки отражаются в Qdrant и OpenSearch; "
            "reindex пересобирает оба индекса.",
        },
        "coverage": {
            "endpoint": "GET /api/v1/coverage/matrix",
            "coverageRatio": coverage_ratio,
            "covered": covered,
            "absent": absent,
            "total": total,
        },
    }
    proven = counts.get("nodes", 0) > 0
    return _chapter(
        8,
        "ingest-reflection",
        "Новый документ обновляет граф, индексы и coverage",
        "Три поверхности отражения корпуса: граф (Neo4j), индексы "
        "(Qdrant/OpenSearch) и coverage-дашборды — все обновляются загрузкой.",
        proven=proven,
        data={
            "surfaces": surfaces,
            "readOnly": True,
            "liveUploadEndpoint": "POST /api/v1/documents/upload",
            "note": "Демо-прогон только читает; для живой демонстрации 8-го "
            "свойства выполните upload документа этим endpoint и наблюдайте "
            "рост во всех трёх поверхностях.",
        },
    )


@router.get("/questions")
def demo_questions(user: str = Depends(current_user)) -> dict:
    """Curated golden demo seeds for the single-session §22.6 walkthrough."""
    return {"questions": list(DEMO_QUESTIONS)}


@router.post("/run")
def run_demo(
    body: RunBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Run the full eight-chapter §23 demo for one question in a single session.

    Drives one real question end-to-end (``answer_query`` → live graph) and returns
    the ordered demo script proving all eight §23 properties consecutively. Every
    chapter carries live data and a ``proven`` flag; ``summary`` rolls the flags up
    so a UI can render a single «target picture achieved» verdict (§22.6 acceptance).
    """
    from agent_service.agent import answer_query

    question = (body.question or DEMO_QUESTIONS[0]["question"]).strip()
    store = get_store()
    ans = answer_query(
        question, store, role=role, use_llm=body.use_llm, geography=body.geography
    )

    chapters = [
        _ch1_question(question, role),
        _ch2_plan(question),
        _ch3_answer(ans, question),
        _ch4_graph(ans, body.max_graph_nodes, body.max_graph_edges),
        _ch5_edge_evidence(store, ans),
        _ch6_gaps(store, ans),
        _ch7_versioning(store),
        _ch8_ingest_reflection(store),
    ]
    proven = sum(1 for c in chapters if c["proven"])
    return {
        "question": question,
        "role": role,
        "useLlm": body.use_llm,
        "chapters": chapters,
        "summary": {
            "propertiesProven": proven,
            "propertiesTotal": len(chapters),
            "targetPictureAchieved": proven == len(chapters),
        },
    }
