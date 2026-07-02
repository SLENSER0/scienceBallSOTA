"""Answer synthesis (§24.11): retrieval result → grounded, cited AnswerPayload.

Assigns citation markers to evidence, builds a compact fact context, and asks an
OSS LLM to write a literature-review-style answer that cites every claim and
lists consensus / disagreements / gaps. Falls back to a deterministic template
when no LLM key is configured, so the pipeline always produces an answer.
"""

from __future__ import annotations

from typing import Any

from kg_common import AnswerPayload, Citation, EvidenceRef, get_logger
from kg_extractors.query_parser import QueryIntent
from kg_retrievers.graph_retriever import RetrievalResult

_log = get_logger("synthesize")

SYSTEM = (
    "Ты — ассистент R&D по горно-металлургическим технологиям. Отвечай СТРОГО на "
    "основе предоставленных фактов (FACTS). Не придумывай данные. Каждое утверждение "
    "подкрепляй ссылкой вида [n] на источник из FACTS. Отвечай на языке вопроса "
    "(русский или английский). Структурируй ответ:\n"
    "1) Краткий вывод.\n2) Методы/решения: принцип, применимость, ключевые числовые "
    "показатели с единицами, отечественная/зарубежная практика.\n"
    "3) Консенсус и разногласия (если значения конфликтуют).\n"
    "4) Что неизвестно / пробелы.\n5) Уровень достоверности.\n"
    "Если фактов недостаточно — честно скажи об этом. Не выдумывай источники."
)


def assign_citations(retrieval: RetrievalResult) -> list[Citation]:
    citations: list[Citation] = []
    for i, ev in enumerate(retrieval.evidence, start=1):
        citations.append(
            Citation(
                marker=f"[{i}]",
                evidence=EvidenceRef(
                    evidence_id=ev["id"],
                    source_id=ev.get("doc_id") or ev["id"],
                    doc_id=ev.get("doc_id"),
                    page=ev.get("page"),
                    text=ev.get("text"),
                    confidence=ev.get("confidence", 1.0),
                    evidence_strength=ev.get("evidence_strength"),
                ),
                source_title=ev.get("name") or ev.get("text", "")[:80],
                year=ev.get("year"),
                geography=ev.get("practice_type") or ev.get("country"),
            )
        )
    return citations


def _cite_index(retrieval: RetrievalResult) -> dict[str, str]:
    return {ev["id"]: f"[{i}]" for i, ev in enumerate(retrieval.evidence, start=1)}


def build_context(retrieval: RetrievalResult, cite: dict[str, str]) -> str:
    lines: list[str] = ["FACTS:"]
    # sources
    if retrieval.evidence:
        lines.append("Источники:")
        for ev in retrieval.evidence:
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
    # hybrid passages (unstructured corpus context, §24.9 fallback)
    if getattr(retrieval, "passages", None):
        lines.append("Обзорные фрагменты из корпуса (неструктурированные):")
        for p in retrieval.passages[:5]:
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
                "Решение": s.get("name"),
                "Практика": s.get("practice_type", "unknown"),
                "Ключевой показатель": metric,
                "Применимость": "; ".join(a for a in s.get("applicability", []) if a) or "—",
            }
        )
    return {"columns": ["Решение", "Практика", "Ключевой показатель", "Применимость"], "rows": rows}


def _fallback_markdown(
    intent: QueryIntent, retrieval: RetrievalResult, cite: dict[str, str]
) -> str:
    lines = [f"## Ответ на запрос\n\n> {intent.raw}\n"]
    if retrieval.solutions:
        lines.append("### Найденные технологии/решения\n")
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
    if retrieval.evidence:
        lines.append("\n### Источники\n")
        for ev in retrieval.evidence:
            m = cite.get(ev["id"], "")
            lines.append(f"- {m} {(ev.get('text') or ev.get('name') or '')[:160]}")
    if not retrieval.solutions and not retrieval.facts:
        lines.append("\n_Достаточных структурированных фактов в базе не найдено._")
    return "\n".join(lines)


def build_answer(
    intent: QueryIntent, retrieval: RetrievalResult, *, use_llm: bool = True
) -> AnswerPayload:
    citations = assign_citations(retrieval)
    cite = _cite_index(retrieval)
    context = build_context(retrieval, cite)
    used_models: list[str] = []

    markdown = ""
    if use_llm:
        try:
            from kg_extractors.llm import get_llm

            llm = get_llm()
            user = f"ВОПРОС: {intent.raw}\n\n{context}\n\nСоставь ответ по инструкции."
            markdown = llm.complete(
                user, system=SYSTEM, model=llm._settings.llm_model_synth, max_tokens=1500
            )
            used_models = list(llm.used_models[-1:])
        except Exception as exc:
            _log.warning("synthesize.llm_failed", error=str(exc))
    if not markdown:
        markdown = _fallback_markdown(intent, retrieval, cite)

    # confidence: mean evidence confidence, penalized by gaps/contradictions
    confs = [ev.get("confidence", 0.6) for ev in retrieval.evidence]
    base = sum(confs) / len(confs) if confs else 0.3
    if retrieval.contradictions:
        base *= 0.8
    if not retrieval.evidence:
        base = min(base, 0.3)

    return AnswerPayload(
        answer_markdown=markdown,
        citations=citations,
        graph=retrieval.graph,
        table=_table(retrieval),
        gaps=[{"name": g.get("name"), "type": g.get("gap_type")} for g in retrieval.gaps],
        contradictions=[{"name": c.get("name")} for c in retrieval.contradictions],
        confidence=round(base, 2),
        parsed_query=intent.to_dict(),
        used_models=used_models,
    )
