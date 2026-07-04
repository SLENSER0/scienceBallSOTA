"""§13.23 Панель прозрачности и воспроизводимости прогона / run transparency & replay.

RU: Показывает, **как агент рассуждал, и доказывает, что это воспроизводимо**. Для
одного вопроса роутер прогоняет план научного агента (§5.2.2/§7.5) по живому графу
знаний (server-профиль, Neo4j :8000) и возвращает три вещи, которых нет в плоском
«Ходе мысли» (§17.7) и дереве спанов (§18.3):

* **``tool_trace``** — журнал вызовов инструментов (переиспользует
  :func:`agent_service.tool_trace.traced_tool`, §13.23): что за tool, с какими
  аргументами, старт/финиш, статус (``ok``/``error``), длительность.
* **сгенерированный Cypher** — для КАЖДОЙ стадии показывается ТОЧНЫЙ Cypher-запрос
  (шаблон) и связанные параметры, которые реально исполнились по ``:Node``/``:Rel``.
  Запросы детерминированы (везде ``ORDER BY … LIMIT``), поэтому результат стабилен
  между прогонами — это и есть основа воспроизводимости.
* **детерминированный replay (seed)** — по ``seed`` минтуется стабильный ``trace_id``
  (:func:`kg_common.tracing.root_context`, §18.2): один seed+вопрос → один trace_id.
  Контент прогона (Cypher + параметры + идентичность строк-результатов) хэшируется в
  ``runDigest`` (sha256). Чтобы **доказать** воспроизводимость, план исполняется
  ДВАЖДЫ в одном запросе и дайджесты сравниваются: ``reproducible=true`` ⇔ второй
  прогон дал тот же контент (тайминги не входят в дайджест — они естественно
  различаются, а контент — нет).

Дополнительно фиксируется **версия набора промптов** узлов
(:func:`agent_service.prompt_registry.versions_fingerprint`, §13.23) — промпты
запинены, поэтому прогон повторяем end-to-end (§7.1 repeatable execution).

EN: For one question, execute the agent's §5.2.2 phase plan live, capturing the real
generated Cypher (+ bound params) per phase, a tool_trace, and a content digest; then
replay the plan a second time and compare digests to prove reproducibility. The whole
thing is seeded so the trace_id is stable (same seed+question → same trace_id).

No rewrite of the agent: tool timing/graceful-error come from ``traced_tool`` (§13.23),
ids from ``root_context`` (§18.2), prompt-version fingerprint from ``prompt_registry``
(§13.23), the tokenizer from :mod:`api_gateway.routers.agent_reasoning` (§17.7). The
Cypher shown is the Cypher executed — the panel cannot drift from reality.

Endpoint:

* ``POST /api/v1/agent/run-transparency`` — body ``{"question": ..., "seed": ...}`` →
  ``tool_trace`` + generated Cypher per phase + ``runDigest`` + ``reproducible`` replay.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_user
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

# Cap on the id list threaded into downstream IN-clauses (keeps Cypher params sane and
# the run deterministic — a bounded, ORDER BY-sorted id set).
_ID_CAP = 40


class RunTransparencyBody(BaseModel):
    """POST /run-transparency payload — вопрос + seed для детерминированного replay."""

    question: str
    # Free-form seed: same seed+question → same trace_id and same runDigest. Default "0"
    # keeps the default run reproducible; callers may vary it to fork a fresh trace_id.
    seed: str = "0"


# --------------------------------------------------------------------------- #
# The generated Cypher plan. Each phase carries the EXACT query executed over  #
# :Node/:Rel. Every query is deterministic (explicit ORDER BY before LIMIT) so #
# the row set — hence the run digest — is stable across replays. This is the   #
# «сгенерированный Cypher», shown verbatim in the panel.                       #
# --------------------------------------------------------------------------- #
_CYPHER_RESOLVE = (
    "MATCH (n:Node)\n"
    "WHERE n.name IS NOT NULL\n"
    "  AND NOT n.label IN ['Gap','Evidence','Chunk','Document']\n"
    "  AND any(t IN $tokens WHERE toLower(n.name) CONTAINS t)\n"
    "RETURN n.id AS id, n.name AS name, n.label AS label, n.domain AS domain\n"
    "ORDER BY n.id\n"
    "LIMIT 60"
)
_CYPHER_GRAPH = (
    "MATCH (a:Node)-[r:Rel]-(b:Node)\n"
    "WHERE a.id IN $ids\n"
    "RETURN a.id AS a_id, r.type AS rel, b.id AS b_id, b.name AS b_name, b.label AS b_label\n"
    "ORDER BY a.id, r.type, b.id\n"
    "LIMIT 300"
)
_CYPHER_VECTOR = (
    "MATCH (n:Node)\n"
    "WHERE any(t IN $tokens WHERE\n"
    "      toLower(coalesce(n.name,'')) CONTAINS t\n"
    "      OR toLower(coalesce(n.description,'')) CONTAINS t)\n"
    "RETURN n.id AS id, n.name AS name, n.label AS label, coalesce(n.description,'') AS descr\n"
    "ORDER BY n.id\n"
    "LIMIT 120"
)
_CYPHER_EVIDENCE = (
    "MATCH (f:Node)-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'})\n"
    "WHERE f.id IN $ids\n"
    "RETURN f.id AS fact_id, e.id AS evidence_id, e.doc_id AS doc_id, e.page AS page,\n"
    "       left(coalesce(e.text,''),160) AS text\n"
    "ORDER BY f.id, e.id\n"
    "LIMIT 80"
)
_CYPHER_GAP = (
    "MATCH (g:Node {label:'Gap'})-[:Rel {type:'ABOUT'}]->(s:Node)\n"
    "WHERE s.id IN $ids\n"
    "RETURN g.id AS gap_id, coalesce(g.name,'') AS name, g.gap_type AS gap_type,\n"
    "       s.id AS subject_id, coalesce(s.name,'') AS subject\n"
    "ORDER BY g.id, s.id\n"
    "LIMIT 80"
)

# (phase, tool-registry name, human label, rationale). Order = evidence-first plan.
_PLAN: tuple[tuple[str, str, str, str], ...] = (
    ("resolve", "resolve_entities", "Сопоставление сущностей",
     "Сопоставляет упоминания из вопроса с каноническими сущностями графа."),
    ("graph_query", "run_cypher_template", "Обход графа",
     "Обходит 1-hop окрестность найденных сущностей (соседи, типы рёбер)."),
    ("vector_search", "hybrid_search", "Ретрив фактов",
     "Лексический ретрив по тексту узлов (name/description) — кандидаты-факты."),
    ("evidence_check", "get_evidence_by_ids", "Проверка доказательств",
     "Собирает Evidence (SUPPORTED_BY) под найденные факты — provenance."),
    ("gap_scan", "scan_gaps", "Скан пробелов",
     "Ищет открытые пробелы (Gap ABOUT темы) вокруг вопроса."),
)


def _row(row: Any, i: int) -> Any:
    """Safe positional access into a store row (list/tuple), else ``None``."""
    try:
        return row[i]
    except (IndexError, TypeError, KeyError):
        return None


# --------------------------------------------------------------------------- #
# Per-phase processors — turn raw rows into (display payload, forward ids,     #
# result signature). The signature is a SORTED list of stable ids: it captures #
# the identity of the result independent of DB row order, so the run digest is #
# deterministic. Display payloads feed the expandable «результат» in the UI.   #
# --------------------------------------------------------------------------- #
def _proc_resolve(rows: list[Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    entities = [
        {"id": _row(r, 0), "name": _row(r, 1), "label": _row(r, 2), "domain": _row(r, 3)}
        for r in rows
        if _row(r, 0)
    ]
    ids = [str(e["id"]) for e in entities][:_ID_CAP]
    sig = sorted(ids)
    return {"entities": entities[:20], "count": len(entities)}, ids, sig


def _proc_graph(rows: list[Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    neighbors: list[dict[str, Any]] = []
    rel_types: dict[str, int] = {}
    seen: set[str] = set()
    for r in rows:
        rt = str(_row(r, 1) or "REL")
        rel_types[rt] = rel_types.get(rt, 0) + 1
        b_id = _row(r, 2)
        if b_id and b_id not in seen:
            seen.add(str(b_id))
            neighbors.append(
                {"from": _row(r, 0), "rel": rt, "id": b_id,
                 "name": _row(r, 3), "label": _row(r, 4)}
            )
    ids = [str(n["id"]) for n in neighbors][:_ID_CAP]
    sig = sorted({*ids, *(f"rel:{k}={v}" for k, v in rel_types.items())})
    payload = {"neighbors": neighbors[:24], "relationTypes": rel_types, "count": len(neighbors)}
    return payload, ids, sig


def _proc_vector(rows: list[Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    hits = [
        {"id": _row(r, 0), "name": _row(r, 1), "label": _row(r, 2),
         "snippet": (str(_row(r, 3) or "")[:160]).strip()}
        for r in rows
        if _row(r, 0)
    ]
    ids = [str(h["id"]) for h in hits][:_ID_CAP]
    sig = sorted(ids)
    return {"hits": hits[:12], "count": len(hits)}, ids, sig


def _proc_evidence(rows: list[Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    evidence: list[dict[str, Any]] = []
    facts: set[str] = set()
    for r in rows:
        f_id = _row(r, 0)
        facts.add(str(f_id))
        evidence.append(
            {"factId": f_id, "evidenceId": _row(r, 1), "docId": _row(r, 2),
             "page": _row(r, 3), "text": _row(r, 4)}
        )
    sig = sorted(str(_row(r, 1)) for r in rows if _row(r, 1))
    payload = {"evidence": evidence[:20], "factCount": len(facts), "count": len(evidence)}
    return payload, [], sig


def _proc_gap(rows: list[Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    gaps = [
        {"id": _row(r, 0), "name": _row(r, 1), "gapType": _row(r, 2),
         "subjectId": _row(r, 3), "subject": _row(r, 4)}
        for r in rows
        if _row(r, 0)
    ]
    sig = sorted(str(g["id"]) for g in gaps)
    return {"gaps": gaps[:20], "count": len(gaps)}, [], sig


_PROCESSORS = {
    "resolve": _proc_resolve,
    "graph_query": _proc_graph,
    "vector_search": _proc_vector,
    "evidence_check": _proc_evidence,
    "gap_scan": _proc_gap,
}


def _cypher_for(phase: str, tokens: list[str], entity_ids: list[str],
                scope_ids: list[str]) -> tuple[str, dict[str, Any]]:
    """Return the (deterministic) Cypher template + bound params for ``phase``."""
    if phase == "resolve":
        return _CYPHER_RESOLVE, {"tokens": tokens}
    if phase == "graph_query":
        return _CYPHER_GRAPH, {"ids": entity_ids}
    if phase == "vector_search":
        return _CYPHER_VECTOR, {"tokens": tokens}
    if phase == "evidence_check":
        return _CYPHER_EVIDENCE, {"ids": scope_ids}
    if phase == "gap_scan":
        return _CYPHER_GAP, {"ids": scope_ids}
    return "", {}


def _execute_plan(store: Any, tokens: list[str], clock: Any) -> dict[str, Any]:
    """Run the full §5.2.2 plan once: real Cypher reads + tool_trace + phase payloads.

    Returns the per-phase records (generated Cypher, params, timing, status, result
    payload, result signature), the flat ``tool_trace`` and the ordered signature list
    used to compute the reproducibility digest.
    """
    from agent_service.tool_trace import ToolTraceEntry, traced_tool

    entity_ids: list[str] = []
    scope_ids: list[str] = []
    phases: list[dict[str, Any]] = []
    tool_trace: list[dict[str, Any]] = []
    sig_parts: list[dict[str, Any]] = []
    t0 = clock()

    for phase, tool_name, label, rationale in _PLAN:
        cypher, params = _cypher_for(phase, tokens, entity_ids, scope_ids)

        # Real read, timed + graceful-error-captured by traced_tool (§13.23).
        def _fn(_a: dict[str, Any], _c: str = cypher, _p: dict[str, Any] = params) -> Any:
            return store.rows(_c, _p)

        rows, entry = traced_tool(tool_name, _fn, params, clock)
        rows = rows or []

        payload, fwd_ids, sig = _PROCESSORS[phase](rows if entry.status == "ok" else [])
        # Thread ids forward exactly like the reasoning orchestrator (§17.7).
        if phase == "resolve":
            entity_ids = fwd_ids
            scope_ids = list(entity_ids)
        elif phase == "graph_query":
            scope_ids = list(dict.fromkeys([*entity_ids, *fwd_ids]))[:_ID_CAP]

        # tool_trace row — reuse the immutable ToolTraceEntry projection (§13.23).
        trace_entry = ToolTraceEntry(
            tool=tool_name,
            args=params,
            started_at=entry.started_at,
            finished_at=entry.finished_at,
            status=entry.status,
            summary=_summary(phase, payload, entry.status),
            data_ref=f"phase:{phase}",
            error=entry.error,
        )
        tool_trace.append(trace_entry.as_dict())

        phases.append(
            {
                "phase": phase,
                "tool": tool_name,
                "label": label,
                "rationale": rationale,
                "status": entry.status,
                "iconKey": "done" if entry.status == "ok" else "error",
                "offsetMs": round(entry.started_at - t0, 2),
                "durationMs": trace_entry.duration_ms,
                "cypher": cypher,
                "params": params,
                "rowCount": len(rows),
                "summary": trace_entry.summary,
                "error": entry.error,
                "result": payload,
                "resultSignature": sig,
            }
        )
        # Digest input excludes timings on purpose — content, not latency (see module doc).
        sig_parts.append(
            {"phase": phase, "cypher": cypher, "params": params,
             "status": entry.status, "signature": sig}
        )

    return {
        "phases": phases,
        "toolTrace": tool_trace,
        "sigParts": sig_parts,
        "totalDurationMs": round(clock() - t0, 2),
    }


def _summary(phase: str, payload: dict[str, Any], status: str) -> str:
    """One short human line per phase (used in tool_trace + step header)."""
    if status != "ok":
        return "шаг завершился ошибкой / step failed"
    if phase == "resolve":
        return f"сопоставлено сущностей: {payload.get('count', 0)}"
    if phase == "graph_query":
        return (f"соседей: {payload.get('count', 0)}, "
                f"типов связей: {len(payload.get('relationTypes', {}))}")
    if phase == "vector_search":
        return f"кандидатов-фактов: {payload.get('count', 0)}"
    if phase == "evidence_check":
        return (f"доказательств: {payload.get('count', 0)} "
                f"на {payload.get('factCount', 0)} факт(ов)")
    if phase == "gap_scan":
        return f"открытых пробелов: {payload.get('count', 0)}"
    return phase


def _digest(sig_parts: list[dict[str, Any]]) -> str:
    """Stable sha256 over the canonical (phase, cypher, params, signature) content."""
    blob = json.dumps(sig_parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _prompt_pins() -> dict[str, Any]:
    """Pinned node-prompt versions + fingerprint (§13.23 repeatable execution)."""
    try:
        from agent_service.prompt_registry import active_versions, versions_fingerprint

        return {
            "versions": active_versions(),
            "fingerprint": versions_fingerprint(),
        }
    except Exception:
        return {"versions": {}, "fingerprint": ""}


def _run(store: Any, question: str, seed: str) -> dict[str, Any]:
    """Execute the plan, replay it, and assemble the transparency+reproducibility view."""
    from api_gateway.routers.agent_reasoning import _tokens
    from kg_common.tracing import root_context

    tokens = _tokens(question)
    # Seeded root context → deterministic trace_id (same seed+question → same id, §18.2).
    root = root_context(seed=f"run-transparency/{seed}/{question}")

    clock = lambda: time.perf_counter() * 1000.0  # ms clock  # noqa: E731

    first = _execute_plan(store, tokens, clock)
    run_digest = _digest(first["sigParts"])

    # Deterministic replay: run the identical plan a second time and compare content
    # digests. Timings differ; content must not → proves the run is reproducible.
    second = _execute_plan(store, tokens, clock)
    replay_digest = _digest(second["sigParts"])
    reproducible = run_digest == replay_digest

    status_counts: dict[str, int] = {}
    for p in first["phases"]:
        status_counts[p["status"]] = status_counts.get(p["status"], 0) + 1

    return {
        "question": question,
        "seed": seed,
        "traceId": root.trace_id,
        "rootSpanId": root.span_id,
        "traceparent": root.to_header(),
        "tokens": tokens,
        "phases": first["phases"],
        "toolTrace": first["toolTrace"],
        "phaseCount": len(first["phases"]),
        "statusCounts": status_counts,
        "totalDurationMs": first["totalDurationMs"],
        "promptPins": _prompt_pins(),
        "runDigest": run_digest,
        "replay": {
            "seed": seed,
            "digest": replay_digest,
            "reproducible": reproducible,
            "note": (
                "Второй прогон того же плана дал идентичный контент (Cypher + параметры + "
                "идентичность строк-результатов). Тайминги не входят в дайджест."
                if reproducible
                else "Контент между прогонами различается — граф изменился во время запроса."
            ),
        },
    }


@router.post("/run-transparency")
def run_transparency(body: RunTransparencyBody, user: str = Depends(current_user)) -> dict:
    """Run the §13.23 transparency+reproducibility panel for one question.

    Returns the seeded ``traceId``, a per-phase list carrying the EXACT generated Cypher
    (+ bound params, row count, deterministic result signature and expandable result),
    the ``toolTrace`` (§13.23 tool-call log), the pinned prompt-version fingerprint, and
    a ``replay`` block whose ``reproducible`` flag is proven by re-running the identical
    plan and comparing content digests (``runDigest`` == ``replay.digest``).
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    seed = (body.seed or "0").strip() or "0"
    return _run(get_store(), question, seed)
