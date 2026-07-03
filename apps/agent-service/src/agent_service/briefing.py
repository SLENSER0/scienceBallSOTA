"""Agentic knowledge briefing — командный центр «состояние знаний».

Gathers a compact snapshot of the whole graph (size, per-domain coverage + risk, top
open gaps, notable contradictions, most-connected technologies) and hands it to an
analyst agent that writes a narrative «state of knowledge» briefing: strengths, risk
zones, key open questions and recommendations. The dashboard renders the hard numbers;
the agent adds the story a research lead would tell over them.

Analyst runs on the OSS synth model (DeepSeek-V4-Flash) via OpenRouter (§7.5).
"""

from __future__ import annotations

from typing import Any

from kg_common import get_logger, get_settings

_log = get_logger("briefing")

_GAPS_CYPHER = "MATCH (g:Node {label:'Gap'}) RETURN g.name, g.gap_type, g.domain LIMIT 15"
_TECH_CYPHER = (
    "MATCH (t:Node {label:'TechnologySolution'}) "
    "OPTIONAL MATCH (t)-[r:Rel]-() "
    "WITH t, count(r) AS deg "
    "RETURN t.id, t.name, deg ORDER BY deg DESC LIMIT 8"
)


def gather_snapshot(store: Any) -> dict[str, Any]:
    """Assemble the hard numbers the analyst reasons over (no LLM)."""
    from agent_service.contradiction_analysis import list_contradictions
    from kg_retrievers.coverage_dashboard import build_dashboard

    coverage = build_dashboard(store).as_dict()
    gaps = [{"name": r[0], "type": r[1], "domain": r[2]} for r in store.rows(_GAPS_CYPHER) if r[0]]
    # Fetch a wide slice, then keep the largest-spread conflicts (the ones worth reporting).
    contradictions = sorted(
        list_contradictions(store, limit=40), key=lambda c: c.get("spread", 0), reverse=True
    )[:12]
    techs = [{"id": r[0], "name": r[1], "degree": int(r[2] or 0)} for r in store.rows(_TECH_CYPHER)]
    return {
        "counts": store.counts(),
        "byLabel": store.counts_by_label(),
        "coverage": coverage,
        "gaps": gaps,
        "contradictions": contradictions,
        "topTechnologies": techs,
    }


_BRIEF_SYSTEM = (
    "Ты — научный аналитик R&D в горном деле и металлургии. По снапшоту графа знаний "
    "напиши сжатый обзор по-русски в markdown. ПРАВИЛА: (1) используй ТОЛЬКО числа из "
    "снапшота; не выдумывай знаменателей и итогов — общие счётчики даны явно. (2) Про "
    "противоречия пиши истинные диапазоны (min–max) из данных, в первую очередь самый "
    "большой спред. (3) Если единица измерения не подходит показателю (напр. «мм» для "
    "концентрации) — отметь это как вероятную ошибку извлечения, а не как факт. Разделы: "
    "**Обзор** (объём базы, домены); **Сильные стороны**; **Зоны риска** (домены с малым "
    "числом источников — назови); **Ключевые открытые вопросы** (пробелы); **Заметные "
    "противоречия** (с диапазонами); **Рекомендации** (2–3 приоритета)."
)


def _prompt(snap: dict[str, Any]) -> str:
    cov = snap["coverage"]
    totals = cov.get("totals", {})
    doms = "; ".join(
        f"{d['domain']}: источников {d['sources']}, измерений {d['measurements']}, "
        f"пробелов {d['gaps']}{' [РИСК]' if d.get('risk') == 'high' else ''}"
        for d in cov.get("by_domain", [])[:10]
    )
    # Gap-type breakdown so the agent doesn't invent denominators.
    from collections import Counter

    gtypes = Counter(g.get("type") or "?" for g in snap["gaps"])
    gtype_str = ", ".join(f"{k}: {v}" for k, v in gtypes.most_common())
    gaps = "; ".join(g["name"] for g in snap["gaps"][:10])
    # Contradictions WITH their true value spread (biggest first).
    contras = "; ".join(
        f"{c['name']} [диапазон {min(c['values'])}–{max(c['values'])} {c.get('unit') or ''}]"
        if c.get("values")
        else c["name"]
        for c in sorted(snap["contradictions"], key=lambda c: c.get("spread", 0), reverse=True)[:8]
    )
    techs = ", ".join(t["name"] for t in snap["topTechnologies"][:8])
    return (
        f"ИТОГИ (используй только их): узлов {snap['counts'].get('nodes')}, "
        f"связей {snap['counts'].get('rels')}, всего пробелов {totals.get('gaps')}, "
        f"всего противоречий {totals.get('contradictions')}.\n"
        f"Домены: {doms}\n"
        f"Зоны риска (мало источников): {', '.join(cov.get('risk_domains', [])) or 'нет'}\n"
        f"Пробелы по типам: {gtype_str}\n"
        f"Примеры пробелов: {gaps}\n"
        f"Крупнейшие противоречия: {contras}\n"
        f"Ключевые технологии (по связям): {techs}\n\n"
        "Напиши обзор состояния знаний."
    )


def generate_briefing(store: Any) -> dict[str, Any]:
    """Return the snapshot plus the analyst agent's narrative briefing."""
    snap = gather_snapshot(store)
    briefing, model = "", None
    try:
        from kg_extractors.llm import get_llm

        llm = get_llm()
        briefing = llm.complete(
            _prompt(snap),
            system=_BRIEF_SYSTEM,
            model=get_settings().llm_model_synth,
            max_tokens=1400,
        )
        model = llm.used_models[-1] if llm.used_models else None
    except Exception as exc:
        _log.warning("briefing.failed", error=str(exc)[:120])
        briefing = "Аналитический обзор недоступен (модель). Показаны метрики ниже."

    return {"snapshot": snap, "briefing": briefing, "model": model}
