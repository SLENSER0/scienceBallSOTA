"""Live agent reasoning trace — «как агент думает по шагам» (§17.7, SOTA #7).

RU: Показывает НАСТОЯЩИЙ ход мысли научного агента как таймлайн из пяти §5.2.2-
стадий — ``resolved entities → graph query → vector search → evidence check →
gap scan``. В отличие от планового таймлайна (`agent_timeline.py`, который лишь
предсказывает последовательность tools по интенту, без исполнения), этот роутер
РЕАЛЬНО прогоняет каждую стадию по живому графу знаний (server-профиль, Neo4j
:8000) и возвращает фактические тайминги, статусы (done/error) и раскрываемые
детали каждого шага (args / summary / dataRef) — главный «агентный» вау-эффект и
доверие к чату.

EN: Executes the five §5.2.2 reasoning phases against the live knowledge graph and
returns the captured ``tool_trace`` projected into the §17.7 chat timeline. No
rewrite: it reuses the agent's own tracing primitives —
:func:`agent_service.tool_trace.traced_tool` / :class:`~agent_service.tool_trace.ToolTraceEntry`
(§13.23, timing + graceful error capture) and
:func:`agent_service.tool_timeline.build_tool_timeline` (§17.7, ordering + §5.2.2
labels + status icons + offsets) — feeding them a trace of real graph reads.

Each phase is a genuine Cypher read over ``:Node {id,label,name,…}`` / ``:Rel {type}``
(the same schema `/gaps`, `/evidence`, `/gap-closure` use):

* ``resolve``        — fuzzy-match question tokens to canonical entities.
* ``graph_query``    — 1-hop neighbourhood + relation types of the resolved entities.
* ``vector_search``  — lexical retrieval over node ``name``/``description`` (a live,
  dependency-free stand-in for hybrid/vector retrieval when Qdrant is not attached;
  ranked by token overlap — honest lexical fallback, disclosed as such).
* ``evidence_check`` — provenance: ``SUPPORTED_BY`` Evidence spans for the facts.
* ``gap_scan``       — open ``Gap`` nodes ``ABOUT`` the topic.

A failing phase never crashes the endpoint (``traced_tool`` swallows the error into a
``status='error'`` step), so the timeline always renders — even on a sparse graph or a
non-Neo4j profile where a Cypher builtin is unsupported.

Endpoint:

* ``POST /api/v1/agent/reasoning-trace`` — body ``{"question": ...}`` → the executed
  timeline (``intent`` header + ``stages`` legend + ordered ``steps`` with timings).
"""

from __future__ import annotations

import dataclasses
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

# The five §5.2.2 phases in fixed left-to-right order. The tool *names* are chosen to
# hit :data:`agent_service.tool_timeline.STEP_LABELS` directly, so ``build_tool_timeline``
# stamps the canonical UI label ("resolved entities" …) on each executed step.
STAGE_ORDER: tuple[str, ...] = (
    "resolve",
    "graph_query",
    "vector_search",
    "evidence_check",
    "gap_scan",
)

# Short human rationale per phase — «что делает этот шаг» for the expandable row.
STAGE_RATIONALE: dict[str, str] = {
    "resolve": "Сопоставляет упоминания из вопроса с каноническими сущностями графа.",
    "graph_query": "Обходит связи графа знаний вокруг найденных сущностей (соседи, типы рёбер).",
    "vector_search": "Лексический поиск по тексту узлов (name/description) — ретрив фактов.",
    "evidence_check": "Собирает доказательства (SUPPORTED_BY → Evidence) под найденные факты.",
    "gap_scan": "Ищет открытые пробелы (Gap ABOUT темы) вокруг вопроса.",
}

# Stopwords (ru + en) dropped before token matching. Small, deterministic, no NLTK.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "what", "which", "how", "does", "did", "are", "was",
        "into", "from", "that", "this", "have", "has", "will", "can", "about", "when",
        "и", "в", "во", "на", "по", "что", "как", "для", "при", "это", "или",
        "какой", "какая", "какие", "чем", "где", "есть", "быть", "если", "над", "под",
    }
)
_TOKEN_RE = re.compile(r"[0-9a-zA-Zа-яёА-ЯЁ]+")

# Cap on the id list threaded into downstream IN-clauses (keeps Cypher params sane).
_ID_CAP = 40


class ReasoningBody(BaseModel):
    """POST /reasoning-trace payload — вопрос пользователя / the user's question."""

    question: str


def _tokens(question: str) -> list[str]:
    """Lower-cased content tokens of ``question`` (stopwords + <3-char dropped)."""
    seen: list[str] = []
    for raw in _TOKEN_RE.findall(question.lower()):
        if len(raw) < 3 or raw in _STOPWORDS or raw in seen:
            continue
        seen.append(raw)
    return seen[:12]


def _overlap(text: str, tokens: list[str]) -> int:
    """How many distinct ``tokens`` appear in ``text`` (lexical relevance score)."""
    low = text.lower()
    return sum(1 for t in tokens if t in low)


# --------------------------------------------------------------------------- #
# Phase implementations — each a real Cypher read; returns a JSON-safe dict.   #
# --------------------------------------------------------------------------- #
def _resolve(store: Any, tokens: list[str]) -> dict[str, Any]:
    """Fuzzy-match question tokens to canonical entities (excludes Gap/Evidence)."""
    if not tokens:
        return {"entities": []}
    rows = store.rows(
        "MATCH (n:Node) "
        "WHERE n.name IS NOT NULL "
        "AND NOT n.label IN ['Gap','Evidence','Chunk','Document'] "
        "AND any(t IN $tokens WHERE toLower(n.name) CONTAINS t) "
        "RETURN n.id, n.name, n.label, n.domain LIMIT 60",
        {"tokens": tokens},
    )
    scored = [
        {
            "id": r[0],
            "name": r[1],
            "label": r[2],
            "domain": r[3],
            "score": _overlap(str(r[1] or ""), tokens),
        }
        for r in rows
        if r[0]
    ]
    scored.sort(key=lambda e: (-e["score"], str(e["name"] or "")))
    return {"entities": scored[:10]}


def _graph_query(store: Any, ids: list[str]) -> dict[str, Any]:
    """1-hop neighbourhood + relation-type tally around the resolved entities."""
    if not ids:
        return {"neighbors": [], "relationTypes": {}}
    rows = store.rows(
        "MATCH (a:Node)-[r:Rel]-(b:Node) WHERE a.id IN $ids "
        "RETURN a.id, r.type, b.id, b.name, b.label LIMIT 300",
        {"ids": ids},
    )
    neighbors: list[dict[str, Any]] = []
    rel_types: dict[str, int] = {}
    seen: set[str] = set()
    for a_id, rtype, b_id, b_name, b_label in rows:
        rt = str(rtype or "REL")
        rel_types[rt] = rel_types.get(rt, 0) + 1
        if b_id and b_id not in seen:
            seen.add(b_id)
            neighbors.append(
                {"from": a_id, "rel": rt, "id": b_id, "name": b_name, "label": b_label}
            )
    return {"neighbors": neighbors[:40], "relationTypes": rel_types}


def _vector_search(store: Any, tokens: list[str]) -> dict[str, Any]:
    """Lexical retrieval over node name+description, ranked by token overlap."""
    if not tokens:
        return {"hits": []}
    rows = store.rows(
        "MATCH (n:Node) "
        "WHERE any(t IN $tokens WHERE "
        "toLower(coalesce(n.name,'')) CONTAINS t "
        "OR toLower(coalesce(n.description,'')) CONTAINS t) "
        "RETURN n.id, n.name, n.label, coalesce(n.description,'') LIMIT 120",
        {"tokens": tokens},
    )
    hits = []
    for nid, name, label, desc in rows:
        if not nid:
            continue
        score = _overlap(f"{name or ''} {desc or ''}", tokens)
        hits.append(
            {
                "id": nid,
                "name": name,
                "label": label,
                "snippet": (str(desc or "")[:160]).strip(),
                "score": score,
            }
        )
    hits.sort(key=lambda h: (-h["score"], str(h["name"] or "")))
    return {"hits": hits[:8]}


def _evidence_check(store: Any, ids: list[str]) -> dict[str, Any]:
    """SUPPORTED_BY provenance: Evidence spans backing the resolved/related facts."""
    if not ids:
        return {"evidence": [], "factCount": 0}
    rows = store.rows(
        "MATCH (f:Node)-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
        "WHERE f.id IN $ids "
        "RETURN f.id, e.id, e.doc_id, e.page, left(coalesce(e.text,''),160) LIMIT 80",
        {"ids": ids},
    )
    facts: set[str] = set()
    evidence = []
    for f_id, e_id, doc_id, page, text in rows:
        facts.add(f_id)
        evidence.append(
            {"factId": f_id, "evidenceId": e_id, "docId": doc_id, "page": page, "text": text}
        )
    return {"evidence": evidence[:20], "factCount": len(facts)}


def _gap_scan(store: Any, ids: list[str]) -> dict[str, Any]:
    """Open Gap nodes ABOUT the resolved/related entities (missing-data scan)."""
    if not ids:
        return {"gaps": []}
    rows = store.rows(
        "MATCH (g:Node {label:'Gap'})-[:Rel {type:'ABOUT'}]->(s:Node) "
        "WHERE s.id IN $ids "
        "RETURN g.id, coalesce(g.name,''), g.gap_type, s.id, coalesce(s.name,'') LIMIT 80",
        {"ids": ids},
    )
    gaps = [
        {"id": r[0], "name": r[1], "gapType": r[2], "subjectId": r[3], "subject": r[4]}
        for r in rows
        if r[0]
    ]
    return {"gaps": gaps[:20]}


# --------------------------------------------------------------------------- #
# Summaries — one short human line per phase from its result.                  #
# --------------------------------------------------------------------------- #
def _summarize(name: str, result: dict[str, Any] | None) -> str:
    """A concise §5.2.2 summary for one executed phase (used as the step summary)."""
    if result is None:
        return "шаг завершился ошибкой / step failed"
    if name == "resolve":
        ents = result["entities"]
        names = ", ".join(str(e["name"]) for e in ents[:3])
        return f"сопоставлено сущностей: {len(ents)}" + (f" ({names})" if names else "")
    if name == "graph_query":
        n = len(result["neighbors"])
        rt = len(result["relationTypes"])
        return f"соседей: {n}, типов связей: {rt}"
    if name == "vector_search":
        h = result["hits"]
        return f"релевантных фактов: {len(h)}"
    if name == "evidence_check":
        return f"доказательств: {len(result['evidence'])} на {result['factCount']} факт(ов)"
    if name == "gap_scan":
        return f"открытых пробелов: {len(result['gaps'])}"
    return name


def _run_trace(store: Any, question: str) -> dict[str, Any]:
    """Execute the five §5.2.2 phases live and project them into the §17.7 timeline."""
    from agent_service.tool_timeline import build_tool_timeline
    from agent_service.tool_trace import traced_tool

    # Milliseconds clock: ``build_tool_timeline`` treats stamps as ms (offsetMs /
    # totalDurationMs), so we feed ms and recompute each step's duration_ms from the
    # same stamps (ToolTraceEntry.duration_ms assumes *seconds*, hence the override).
    clock = lambda: time.perf_counter() * 1000.0  # noqa: E731
    tokens = _tokens(question)

    trace: list[dict[str, Any]] = []

    def _step(name: str, fn: Any, args: dict[str, Any]) -> dict[str, Any] | None:
        result, entry = traced_tool(name, fn, args, clock)
        entry = dataclasses.replace(
            entry, summary=_summarize(name, result), data_ref=f"reasoning:{name}"
        )
        row = entry.as_dict()
        row["duration_ms"] = max(0, round(entry.finished_at - entry.started_at))
        row["rationale"] = STAGE_RATIONALE[name]
        # Bulky phase output, carried through for the expandable step (args/summary/dataRef).
        row["detail"] = result if result is not None else {"error": entry.error}
        trace.append(row)
        return result

    # 1) resolve → entity ids thread into every downstream phase.
    res = _step("resolve", lambda a: _resolve(store, a["tokens"]), {"tokens": tokens})
    entity_ids = [e["id"] for e in (res or {}).get("entities", []) if e.get("id")][:_ID_CAP]

    # 2) graph query → related ids widen the evidence/gap scope.
    gq = _step("graph_query", lambda a: _graph_query(store, a["ids"]), {"ids": entity_ids})
    related_ids = [n["id"] for n in (gq or {}).get("neighbors", []) if n.get("id")]
    scope_ids = list(dict.fromkeys([*entity_ids, *related_ids]))[:_ID_CAP]

    # 3) vector search runs on the raw question tokens (retrieval stage).
    _step("vector_search", lambda a: _vector_search(store, a["tokens"]), {"tokens": tokens})

    # 4) evidence + 5) gap scan run over the resolved+related scope.
    _step("evidence_check", lambda a: _evidence_check(store, a["ids"]), {"ids": scope_ids})
    _step("gap_scan", lambda a: _gap_scan(store, a["ids"]), {"ids": scope_ids})

    timeline = build_tool_timeline(trace)
    payload = timeline.as_dict()
    payload["tokens"] = tokens
    return payload


def _intent_header(question: str) -> dict[str, Any] | None:
    """Best-effort §13.8 intent classification — «почему» such a plan (non-fatal)."""
    try:
        from agent_service.intent_taxonomy import classify_intent_v2

        ir = classify_intent_v2(question)
        return {"intent": ir.intent.value, "confidence": ir.confidence, "matched": list(ir.matched)}
    except Exception:  # classification is a nice-to-have header, never block the trace
        return None


@router.post("/reasoning-trace")
def agent_reasoning_trace(body: ReasoningBody, user: str = Depends(current_user)) -> dict:
    """Run the live §5.2.2 reasoning trace for a question and return the §17.7 timeline.

    The response carries the classified ``intent`` header (why this plan), the canonical
    five-stage ``stages`` legend, the extracted ``tokens``, and the executed ``steps`` —
    each an ordered phase with its real ``duration_ms``, ``status``/``iconKey``, ``args``,
    ``summary``, ``rationale`` and expandable ``detail`` (dataRef payload).
    """
    from agent_service.tool_timeline import STEP_LABELS

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")

    timeline = _run_trace(get_store(), question)
    return {
        "question": question,
        "intent": _intent_header(question),
        "stages": [{"id": sid, "label": STEP_LABELS[sid]} for sid in STAGE_ORDER],
        **timeline,
    }
