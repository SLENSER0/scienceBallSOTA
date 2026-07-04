"""Answer synthesis (§24.11): retrieval result → grounded, cited AnswerPayload.

Assigns citation markers to evidence, builds a compact fact context, and asks an
OSS LLM to write a literature-review-style answer that cites every claim and
lists consensus / disagreements / gaps. Falls back to a deterministic template
when no LLM key is configured, so the pipeline always produces an answer.
"""

from __future__ import annotations

import re
from typing import Any

from agent_service.text_quality import clean_fraction, is_clean_text
from kg_common import AnswerPayload, Citation, EvidenceRef, get_logger
from kg_extractors.query_parser import QueryIntent
from kg_retrievers.graph_retriever import RetrievalResult

_log = get_logger("synthesize")

SYSTEM = (
    "Ты — ассистент R&D по горно-металлургическим технологиям. Отвечай СТРОГО на "
    "основе предоставленных фактов (FACTS). Не придумывай данные. Каждое утверждение "
    "подкрепляй ссылкой вида [n] на источник из FACTS. Отвечай на языке вопроса "
    "(русский или английский). Структурируй ответ по разделам:\n"
    "1) Краткий вывод.\n"
    "2) Эксперименты и условия: что изучали и при каких режимах — температуры, "
    "концентрации, скорости и прочие параметры.\n"
    "3) Оборудование и материалы: используемые установки, реагенты и материалы.\n"
    "4) Методы/решения: принцип, применимость, ключевые числовые показатели с "
    "единицами, отечественная/зарубежная практика.\n"
    "5) Публикации и источники: на какие работы опирается ответ.\n"
    "6) Противоречия (если значения конфликтуют).\n"
    "7) Незакрытые пробелы: чего в данных не хватает.\n"
    "8) Уровень достоверности.\n"
    "Если фактов недостаточно — честно скажи об этом. Не выдумывай источники.\n"
    "ЗАПРЕЩЕНО: помечать числа тегами вида [global], [foreign], [FACTS], [unknown], "
    "[числовые факты] — это НЕ ссылки. Ссылкой считается ТОЛЬКО [n] на конкретный "
    "источник из FACTS. Любое числовое значение без ссылки [n] приводить нельзя: либо "
    "укажи [n], либо не называй число. Если нужных данных в FACTS нет — прямо напиши "
    "об этом и не подставляй правдоподобные значения."
)


# --- grounding-hardening helpers (see agent_service.text_quality) -------------
def _citable_evidence(retrieval: RetrievalResult) -> list[dict[str, Any]]:
    """Real, readable evidence: drop the RBAC notice and OCR/extraction junk.

    A span whose ``text`` is present but unreadable — ``(cid:NN)`` glyph fallbacks,
    dotted TOC leaders, shattered word-spacing — is excluded so it never becomes a
    numbered citation nor is fed to the LLM as a source. Structured sources that
    carry only a name (no text) are kept: their title is meaningful, not noise.
    """
    out: list[dict[str, Any]] = []
    for ev in retrieval.evidence:
        if ev.get("id") == "restricted:notice":
            continue
        text = ev.get("text") or ""
        # Keep a span with junk text only if it still carries real provenance: a
        # structured table cell (table_id / row_index — short cells like «148 HV» are
        # not prose but are valid citations) or a meaningful source name. Otherwise a
        # present-but-unreadable text (``(cid:NN)`` etc.) is dropped.
        if text and not is_clean_text(text):
            structured = ev.get("table_id") is not None or ev.get("row_index") is not None
            if not structured and not is_clean_text(ev.get("name") or ""):
                continue
        out.append(ev)
    return out


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(s or "")}


def _intent_terms(intent: QueryIntent) -> set[str]:
    """Meaningful (≥4-char) query terms: raw question tokens + matched entity names."""
    terms = _tokens(getattr(intent, "raw", "") or "")
    for e in getattr(intent, "entities", []) or []:
        nm = getattr(e, "canonical_en", None)
        if nm is None and isinstance(e, dict):
            nm = e.get("name")
        terms |= _tokens(nm or "")
    return {t for t in terms if len(t) >= 4}


def _relevant_gaps(intent: QueryIntent, gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only gaps lexically tied to the question — never a generic backlog.

    The retriever attaches a Gap node for every matched candidate, so an off-target
    match (generic smelting nodes on a water-treatment question) drags in unrelated
    «gaps». Keep a gap only when its name shares a meaningful stem with the question
    or a matched entity. If the intent has no usable terms we can't judge relevance,
    so the original list is returned unchanged (no worse than before).
    """
    if not gaps:
        return []
    terms = _intent_terms(intent)
    if not terms:
        return list(gaps)
    def _overlaps(t: str, w: str) -> bool:
        return t == w or (len(t) >= 5 and t in w) or (len(w) >= 5 and w in t)

    kept: list[dict[str, Any]] = []
    for g in gaps:
        gtok = _tokens(g.get("name") or "")
        if any(_overlaps(t, w) for t in terms for w in gtok):
            kept.append(g)
    return kept


def _clean_passages(retrieval: RetrievalResult) -> list[dict[str, Any]]:
    return [p for p in (getattr(retrieval, "passages", None) or []) if is_clean_text(p.get("text"))]


def _out_of_coverage(retrieval: RetrievalResult, citable: list[dict[str, Any]]) -> bool:
    """True when nothing readable — evidence, facts, solutions or clean passages — remains."""
    return not (
        citable or retrieval.facts or retrieval.solutions or _clean_passages(retrieval)
    )


def _calibrated_confidence(
    retrieval: RetrievalResult, citable: list[dict[str, Any]], rel_gaps: list[dict[str, Any]]
) -> float:
    """Confidence reflects how much *readable* support the answer stands on (§13.17+).

    The old formula was a flat mean of evidence confidence (~0.49 whether the corpus
    answered the question or returned nothing — a useless signal). Here it rises with
    the amount of clean, structured support and the readable fraction of retrieved
    evidence, and falls with OCR-noise, missing data and contradictions.
    """
    facts = retrieval.facts or []
    sols = retrieval.solutions or []
    support = len(citable) + len(facts) + len(sols) + len(_clean_passages(retrieval))
    if support == 0:
        return 0.1  # corpus does not cover this question — a grounded refusal
    confs = [c for ev in citable if (c := ev.get("confidence")) is not None] or [0.5]
    mean_conf = sum(confs) / len(confs)
    # Readable fraction is judged over spans that actually carry text; structured /
    # named sources with no text (patents, standards) aren't "junk" and must not drag
    # cf toward 0 — that would silently cut a legitimate answer's confidence by ~45%.
    real_ev = (ev for ev in retrieval.evidence if ev.get("id") != "restricted:notice")
    all_text = [t for t in (ev.get("text") for ev in real_ev) if t]
    cf = clean_fraction(all_text) if all_text else 1.0
    quantity = min(1.0, support / 6.0)  # a couple of signals shouldn't read as certain
    base = mean_conf * quantity * (0.55 + 0.45 * cf)
    base *= 1.0 - 0.05 * min(len(rel_gaps), 4)  # up to −20 % for many open gaps
    if retrieval.contradictions:
        base *= 0.85
    # Floor a real (support>0) answer ABOVE the 0.1 grounded-refusal level, so a
    # thinly-supported real answer never reads as less certain than «no data».
    return round(max(0.15, min(0.9, base)), 2)


def _out_of_coverage_markdown(intent: QueryIntent, retrieval: RetrievalResult) -> str:
    """Deterministic grounded refusal when the corpus has no readable support.

    Emitted INSTEAD of calling the LLM, so an empty/junk retrieval can't be padded
    with plausible-but-fabricated numbers (the benchmark's worst failure mode).
    """
    q = (getattr(intent, "raw", "") or "").strip()
    return "\n".join(
        [
            "### Краткий вывод",
            "",
            f"В доступном корпусе нет данных, релевантных запросу «{q}». "
            "Чтобы не выдавать недостоверные сведения, система не формирует ответ по "
            "существу и не приводит числовых значений по этому вопросу.",
            "",
            "### Что нужно, чтобы ответить",
            "- Загрузить в корпус профильные источники по теме запроса "
            "(обзоры, статьи, патенты, техрегламенты).",
            "- Либо использовать внешний поиск / веб-контур для этого вопроса.",
            "",
            "_Подтверждённых фактов в корпусе по этому вопросу не найдено (грунтованный отказ)._",
        ]
    )


def assign_citations(retrieval: RetrievalResult) -> list[Citation]:
    citations: list[Citation] = []
    # Cite only real, readable sources: the RBAC notice and OCR/extraction junk
    # (``(cid:NN)`` etc.) are excluded so garbage never becomes a numbered citation.
    real_ev = _citable_evidence(retrieval)
    for i, ev in enumerate(real_ev, start=1):
        citations.append(
            Citation(
                marker=f"[{i}]",
                evidence=EvidenceRef(
                    evidence_id=ev["id"],
                    source_id=ev.get("doc_id") or ev["id"],
                    doc_id=ev.get("doc_id"),
                    page=ev.get("page"),
                    # M6: surface table-cell coordinates so the UI can flag a «таблица» citation
                    table_id=ev.get("table_id"),
                    row_index=ev.get("row_index"),
                    col_index=ev.get("col_index"),
                    text=ev.get("text"),
                    confidence=ev.get("confidence", 1.0),
                    evidence_strength=ev.get("evidence_strength"),
                ),
                source_title=ev.get("name") or ev.get("text", "")[:80],
                year=ev.get("year") or ev.get("source_year"),
                geography=ev.get("practice_type") or ev.get("country"),
                as_of=(ev.get("source_date") or "")[:10] or None,  # ISO date → YYYY-MM-DD
                # M10: the four separated dates, each with a sensible fallback key.
                publication_date=ev.get("publication_date") or ev.get("source_date"),
                file_modified_date=ev.get("file_modified_date"),
                ingestion_date=ev.get("ingestion_date") or ev.get("created_at"),
                last_verified_at=ev.get("last_verified_at"),
            )
        )
    return citations


def _cite_index(retrieval: RetrievalResult) -> dict[str, str]:
    # Same citable set as assign_citations, so markers stay aligned 1:1.
    real_ev = _citable_evidence(retrieval)
    return {ev["id"]: f"[{i}]" for i, ev in enumerate(real_ev, start=1)}


def build_context(retrieval: RetrievalResult, cite: dict[str, str]) -> str:
    lines: list[str] = ["FACTS:"]
    # sources — only real, readable spans (OCR/extraction junk is not a source)
    citable = _citable_evidence(retrieval)
    if citable:
        lines.append("Источники:")
        for ev in citable:
            m = cite.get(ev["id"], "")
            strength = ev.get("evidence_strength", "")
            geo = ev.get("practice_type") or ev.get("country") or ""
            txt = (ev.get("text") or ev.get("name") or "")[:200]
            lines.append(f"  {m} {txt} ({strength}, {geo}, стр.{ev.get('page', '?')})")
    # solutions
    if retrieval.solutions:
        lines.append("Технологии/методы:")
        for s in retrieval.solutions:
            metrics = "; ".join(
                f"{m.get('name')}={m.get('value_normalized')} {m.get('normalized_unit', '')}"
                for m in s.get("measurements", [])
            )
            appl = "; ".join(a for a in s.get("applicability", []) if a)
            lines.append(
                f"  - {s.get('name')} [{s.get('practice_type', 'unknown')}] "
                f"метрики: {metrics or '—'}; применимость: {appl or '—'}"
            )
    # facts (measurements)
    if retrieval.facts:
        lines.append("Числовые факты:")
        for f in retrieval.facts:
            subj = f.subjects[0].get("name") if f.subjects else ""
            evs = " ".join(cite.get(e["id"], "") for e in f.evidence)
            n = f.node
            lines.append(
                f"  - {subj}: {n.get('name')} = {n.get('value_normalized')} "
                f"{n.get('normalized_unit', '')} {evs}"
            )
    # contradictions
    if retrieval.contradictions:
        lines.append("Противоречия:")
        for c in retrieval.contradictions:
            lines.append(f"  - {c.get('name')}")
    # gaps
    if retrieval.gaps:
        lines.append("Пробелы (нет данных):")
        for g in retrieval.gaps:
            lines.append(f"  - {g.get('name')}")
    # hybrid passages (unstructured corpus context, §24.9 fallback) — readable only
    clean_p = _clean_passages(retrieval)
    if clean_p:
        lines.append("Обзорные фрагменты из корпуса (неструктурированные):")
        for p in clean_p[:5]:
            lines.append(f"  - «{(p.get('text') or '')[:220]}» (док {p.get('doc_id')})")
    return "\n".join(lines)


def _table(retrieval: RetrievalResult) -> dict[str, Any] | None:
    if not retrieval.solutions:
        return None
    rows = []
    for s in retrieval.solutions:
        metric = next(
            (
                f"{m.get('value_normalized')} {m.get('normalized_unit', '')}"
                for m in s.get("measurements", [])
            ),
            "—",
        )
        rows.append(
            {
                # never emit null cells — the frontend TS type declares strings
                "Решение": s.get("name") or s.get("id") or "—",
                "Практика": s.get("practice_type") or "unknown",
                "Ключевой показатель": metric,
                "Применимость": "; ".join(a for a in s.get("applicability", []) if a) or "—",
            }
        )
    return {"columns": ["Решение", "Практика", "Ключевой показатель", "Применимость"], "rows": rows}


def _brief_conclusion(retrieval: RetrievalResult) -> str:
    """A 2–4 line extractive «краткий вывод» from graph facts — no LLM, instant."""
    parts: list[str] = []
    practice_ru = {"russia": "отеч.", "foreign": "заруб.", "global": "межд.", "cis": "СНГ"}
    sols = [s for s in retrieval.solutions[:5] if s.get("name")]
    if sols:

        def _label(s: dict) -> str:
            pt = practice_ru.get(s.get("practice_type"))
            return s["name"] + (f" ({pt})" if pt else "")

        names = ", ".join(_label(s) for s in sols)
        parts.append(f"**Кратко:** по вашим условиям релевантны — {names}.")
    fbits: list[str] = []
    for f in retrieval.facts[:3]:
        n = f.node
        prop = n.get("property_name") or n.get("name")
        val = n.get("value_normalized")
        unit = n.get("normalized_unit") or n.get("unit") or ""
        if prop and val is not None:
            fbits.append(f"{prop} ≈ {val} {unit}".strip())
    if fbits:
        parts.append("Ключевые показатели: " + "; ".join(fbits) + ".")
    if retrieval.contradictions:
        parts.append(f"⚠ Есть противоречивые данные ({len(retrieval.contradictions)}) — см. ниже.")
    if not parts:
        return ""
    parts.append("_Подробный разбор с доказательствами формируется…_")
    return " ".join(parts)


def _fallback_markdown(
    intent: QueryIntent, retrieval: RetrievalResult, cite: dict[str, str]
) -> str:
    lines = [f"## Ответ на запрос\n\n> {intent.raw}\n"]
    # 1) Краткий вывод — extractive, straight from the graph facts (no LLM).
    brief = _brief_conclusion(retrieval)
    if brief:
        lines.append("### Краткий вывод\n")
        lines.append(brief + "\n")
    # 2) Эксперименты и условия — наблюдаемые числовые показатели/режимы (facts).
    if retrieval.facts:
        lines.append("### Эксперименты и условия\n")
        for f in retrieval.facts:
            subj = f.subjects[0].get("name") if f.subjects else ""
            n = f.node
            prop = n.get("property_name") or n.get("name")
            val = n.get("value_normalized")
            unit = n.get("normalized_unit") or n.get("unit") or ""
            evs = " ".join(cite.get(e["id"], "") for e in f.evidence)
            lines.append(f"- {subj}: {prop} = {val} {unit} {evs}".rstrip())
    # 3) Оборудование и материалы — условия применимости найденных решений.
    appl_rows = [
        (s.get("name"), "; ".join(a for a in s.get("applicability", []) if a))
        for s in retrieval.solutions
    ]
    appl_rows = [(nm, ap) for nm, ap in appl_rows if ap]
    if appl_rows:
        lines.append("\n### Оборудование и материалы (условия применимости)\n")
        for nm, ap in appl_rows:
            lines.append(f"- **{nm}** — {ap}")
    # 4) Методы/решения.
    if retrieval.solutions:
        lines.append("\n### Найденные технологии/решения\n")
        for s in retrieval.solutions:
            metrics = ", ".join(
                f"{m.get('name')} = {m.get('value_normalized')} {m.get('normalized_unit', '')}"
                for m in s.get("measurements", [])
            )
            lines.append(
                f"- **{s.get('name')}** ({s.get('practice_type', 'unknown')})"
                + (f" — {metrics}" if metrics else "")
            )
    if retrieval.contradictions:
        lines.append("\n### ⚠️ Противоречия\n")
        lines += [f"- {c.get('name')}" for c in retrieval.contradictions]
    if retrieval.gaps:
        lines.append("\n### 🔍 Пробелы в знаниях\n")
        lines += [f"- {g.get('name')}" for g in retrieval.gaps]
    # Only the citable set — symmetric with build_context/assign_citations — so OCR
    # junk and the RBAC notice never leak into the fallback (no-LLM) answer body.
    citable = _citable_evidence(retrieval)
    if citable:
        lines.append("\n### Источники\n")
        for ev in citable:
            m = cite.get(ev["id"], "")
            lines.append(f"- {m} {(ev.get('text') or ev.get('name') or '')[:160]}")
    if not retrieval.solutions and not retrieval.facts:
        lines.append("\n_Достаточных структурированных фактов в базе не найдено._")
    return "\n".join(lines)


def build_answer(
    intent: QueryIntent,
    retrieval: RetrievalResult,
    *,
    use_llm: bool = True,
    reasoning_mode: bool = False,
) -> AnswerPayload:
    citations = assign_citations(retrieval)
    cite = _cite_index(retrieval)
    citable = _citable_evidence(retrieval)
    rel_gaps = _relevant_gaps(intent, retrieval.gaps)
    used_models: list[str] = []
    reasoning = ""

    # Out-of-coverage: no readable evidence, no facts, no solutions, no clean passages.
    # Answer deterministically INSTEAD of calling the LLM, so an empty/junk retrieval
    # can never be padded with plausible-but-fabricated numbers (benchmark's worst case).
    out_of_coverage = _out_of_coverage(retrieval, citable)

    if out_of_coverage:
        markdown = _out_of_coverage_markdown(intent, retrieval)
        confidence = 0.1
    else:
        context = build_context(retrieval, cite)
        markdown = ""
        if use_llm:
            try:
                from kg_extractors.llm import get_llm

                llm = get_llm()
                user = f"ВОПРОС: {intent.raw}\n\n{context}\n\nСоставь ответ по инструкции."
                # Speed path: a plain completion skips the separate chain-of-thought round
                # (which ~doubled latency on the synchronous /query surface). Reasoning is
                # still available on demand via complete_with_reasoning where it's shown.
                if reasoning_mode:
                    markdown, reasoning = llm.complete_with_reasoning(
                        user, system=SYSTEM, model=llm._settings.llm_model_synth, max_tokens=1600
                    )
                else:
                    markdown = llm.complete(
                        user, system=SYSTEM, model=llm._settings.llm_model_synth, max_tokens=1600
                    )
                used_models = list(llm.used_models[-1:])
            except Exception as exc:
                _log.warning("synthesize.llm_failed", error=str(exc))
        if not markdown:
            markdown = _fallback_markdown(intent, retrieval, cite)
        confidence = _calibrated_confidence(retrieval, citable, rel_gaps)

    return AnswerPayload(
        answer_markdown=markdown,
        citations=citations,
        graph=retrieval.graph,
        table=_table(retrieval),
        gaps=[{"name": g.get("name"), "type": g.get("gap_type")} for g in rel_gaps],
        contradictions=[{"name": c.get("name")} for c in retrieval.contradictions],
        confidence=confidence,
        parsed_query=intent.to_dict(),
        used_models=used_models,
        reasoning=reasoning,
    )


def stream_answer(intent: QueryIntent, retrieval: RetrievalResult):
    """Yield ('meta', obj) → ('token', str)* → ('final', dict) for live SSE.

    Same payload as :func:`build_answer`, but the answer text streams token-by-token so
    a brief conclusion shows in a few seconds and the rest fills in as it generates.
    """
    citations = assign_citations(retrieval)
    cite = _cite_index(retrieval)
    citable = _citable_evidence(retrieval)
    rel_gaps = _relevant_gaps(intent, retrieval.gaps)
    # Everything except the answer text — emitted immediately (graph, gaps, citations).
    yield "meta", {
        "graph": retrieval.graph,
        "table": _table(retrieval),
        "gaps": [{"name": g.get("name"), "type": g.get("gap_type")} for g in rel_gaps],
        "contradictions": [{"name": c.get("name")} for c in retrieval.contradictions],
        "citations": citations,
        "parsed_query": intent.to_dict(),
    }

    # Same grounded-refusal guard as build_answer: with no readable support, stream a
    # deterministic refusal and never let the LLM fabricate values (hero-path parity).
    out_of_coverage = _out_of_coverage(retrieval, citable)
    if out_of_coverage:
        markdown = _out_of_coverage_markdown(intent, retrieval)
        yield "token", markdown
        yield "final", {"answer_markdown": markdown, "confidence": 0.1, "used_models": []}
        return

    context = build_context(retrieval, cite)
    # A brief extractive conclusion straight from the graph facts — no LLM wait, so a
    # readable «краткий вывод» shows the moment retrieval finishes; the LLM refines below.
    brief = _brief_conclusion(retrieval)
    if brief:
        yield "brief", {"text": brief}
    parts: list[str] = []
    used_models: list[str] = []
    try:
        from kg_extractors.llm import get_llm

        llm = get_llm()
        user = f"ВОПРОС: {intent.raw}\n\n{context}\n\nСоставь ответ по инструкции."
        # Generous cap so the RU answer (token-heavy Cyrillic) is never cut mid-word;
        # streaming means a larger cap costs nothing until the model actually needs it.
        for piece in llm.complete_stream(
            user, system=SYSTEM, model=llm._settings.llm_model_synth, max_tokens=4000
        ):
            parts.append(piece)
            yield "token", piece
        used_models = list(llm.used_models[-1:])
    except Exception as exc:  # fall back to an extractive answer on stream failure
        _log.warning("synthesize.stream_failed", error=str(exc))
    markdown = "".join(parts).strip()
    if not markdown:
        markdown = _fallback_markdown(intent, retrieval, cite)
        yield "token", markdown
    yield "final", {
        "answer_markdown": markdown,
        "confidence": _calibrated_confidence(retrieval, citable, rel_gaps),
        "used_models": used_models,
    }
