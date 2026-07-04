"""Gap-informed (optionally multimodal) deep research (§5 / library).

The flow the scientist actually wants:

    промпт (+ картинка) → анализ промпта и ТЕКУЩИХ данных корпуса →
    понять, чего НЕТ / на что обратить внимание → веб-поиск по этим пробелам →
    отчёт + найденные статьи (каждую можно «Загрузить в граф»).

Two steps so the UI can show the gap analysis first, then run the search:

* :func:`analyze` — multimodal-enriches the question with an image (MiniMax-M3),
  runs the LIVE graph retrieval to see what the corpus already has + its gaps,
  and asks the OSS LLM for what is MISSING, what to pay attention to, and 3–5
  concrete web-search queries to close the gaps.
* :func:`run` — DuckDuckGo-searches those queries, collects real source URLs, and
  synthesizes a cited report. The returned ``sources`` feed the existing
  «Загрузить в граф» → source-trust → review flow (routers/research.py).
"""

from __future__ import annotations

from typing import Any

from kg_common import get_logger

_log = get_logger("gap-research")


def _corpus_summary(store: Any, question: str) -> dict[str, Any]:
    """What the corpus already HAS for this question — direct 1-hop counts around the
    question's resolved entities (backend-agnostic ``store.rows``, works on Neo4j/Kuzu)."""
    from kg_extractors.query_parser import parse_query

    intent = parse_query(question)
    ent_ids = [
        (e.get("id") if isinstance(e, dict) else getattr(e, "id", None)) for e in (intent.entities or [])
    ]
    ent_ids = [e for e in ent_ids if e]
    solutions: list[str] = []
    gaps: list[str] = []
    n_facts = 0
    n_papers = 0
    for eid in ent_ids[:6]:
        try:
            rows = store.rows(
                "MATCH (a:Node)-[:Rel]-(m:Node) "
                "WHERE (a.id = $id OR a.id ENDS WITH $suf) "
                "AND m.label IN ['Measurement','TechnologySolution','Paper','Gap'] "
                "RETURN m.label AS l, coalesce(m.name, coalesce(m.gap_type,'')) AS nm LIMIT 60",
                {"id": eid, "suf": ":" + str(eid)},
            )
        except Exception as exc:  # pragma: no cover - store defensiveness
            _log.warning("gap_research.retrieve_failed", error=str(exc)[:200])
            continue
        for r in rows:
            lbl, nm = r[0], (r[1] or "")
            if lbl == "TechnologySolution" and nm:
                solutions.append(nm)
            elif lbl == "Measurement":
                n_facts += 1
            elif lbl == "Paper":
                n_papers += 1
            elif lbl == "Gap" and nm:
                gaps.append(nm)
    uniq_sols = list(dict.fromkeys(solutions))
    return {
        "entities": ent_ids[:10],
        "n_solutions": len(uniq_sols),
        "n_facts": n_facts,
        "n_papers": n_papers,
        "n_gaps": len(set(gaps)),
        "solutions": uniq_sols[:8],
        "gaps": list(dict.fromkeys(gaps))[:8],
    }


def analyze(store: Any, question: str, image_data_uri: str | None = None) -> dict[str, Any]:
    """Step 1: enrich with the image, read the corpus, decide what's missing + queries."""
    from kg_extractors.llm import get_llm

    llm = get_llm()
    q = question.strip()
    vision = ""
    if image_data_uri:
        try:
            vision = llm.complete_multimodal(
                "Кратко опиши, что на изображении (график/схема/таблица/микрофото), какие "
                "величины, оси, единицы и подписи видны. 3–5 предложений.",
                [image_data_uri],
                max_tokens=500,
            )
            q = f"{question}\n\n[Из изображения]: {vision}"
        except Exception as exc:
            _log.warning("gap_research.vision_failed", error=str(exc)[:200])

    have = _corpus_summary(store, q)
    have_txt = (
        f"сущности: {', '.join(have['entities']) or '—'}; решений в корпусе: {have['n_solutions']}, "
        f"фактов: {have['n_facts']}, зафиксированных пробелов: {have['n_gaps']}, противоречий: "
        f"{have.get('n_contradictions', 0)}. Примеры решений: {', '.join(str(s) for s in have['solutions']) or '—'}. "
        f"Примеры пробелов: {', '.join(str(g) for g in have['gaps']) or '—'}."
    )

    from kg_common import get_settings
    from kg_extractors.llm import _try_parse_json

    focus: dict[str, Any] = {}
    try:
        # complete_with_reasoning routes to a throughput provider (unlike complete_json),
        # so reasoning models return real content; JSON may land in content or reasoning.
        raw, reasoning = llm.complete_with_reasoning(
            "Верни ТОЛЬКО валидный JSON без markdown, без пояснений, без текста до/после — "
            'ровно с ключами "missing", "attention", "queries" (каждый — массив строк).\n\n'
            f"ВОПРОС: {q}\n\n"
            f"ЧТО УЖЕ ЕСТЬ В КОРПУСЕ: {have_txt}\n\n"
            '"missing" — чего не хватает в корпусе для полного ответа (3–6 пунктов); '
            '"attention" — на что обратить внимание (2–4 пункта); '
            '"queries" — 3–5 конкретных поисковых запросов (RU/EN) для веб-поиска, чтобы закрыть пробелы.\n'
            'Пример формы: {"missing":["..."],"attention":["..."],"queries":["..."]}',
            system="Ты научный аналитик горно-металлургического R&D. Отвечай ТОЛЬКО валидным JSON.",
            model=get_settings().llm_model_extract,
            max_tokens=900,
        )
        focus = _try_parse_json(raw) or _try_parse_json(reasoning) or {}
    except Exception as exc:
        _log.warning("gap_research.analyze_failed", error=str(exc)[:200])

    queries = [str(x) for x in (focus.get("queries") or []) if str(x).strip()][:5]
    if not queries:
        queries = [question.strip()]
    return {
        "question": q,
        "vision": vision,
        "have": have,
        "missing": [str(x) for x in (focus.get("missing") or [])][:8],
        "attention": [str(x) for x in (focus.get("attention") or [])][:8],
        "queries": queries,
    }


def run(question: str, queries: list[str]) -> dict[str, Any]:
    """Step 2: web-search the focus queries, collect real sources, synthesize a report."""
    from api_gateway.deep_search_tool import _ddg_search, collected_sources, reset_found_sources
    from kg_extractors.llm import get_llm

    qs = [str(x) for x in (queries or []) if str(x).strip()][:5] or [question]
    reset_found_sources()
    try:
        search_text = _ddg_search(qs, 5)
    except Exception as exc:
        _log.warning("gap_research.search_failed", error=str(exc)[:200])
        search_text = "(веб-поиск недоступен)"
    sources = collected_sources()

    report = ""
    try:
        llm = get_llm()
        content, reasoning = llm.complete_with_reasoning(
            f"Вопрос: {question}\n\nРезультаты веб-поиска (нумерованы по источникам):\n"
            f"{search_text[:6000]}\n\n"
            "Составь структурированный научный обзор по-русски: методы/технологии, числовые "
            "условия и параметры, места применения (отеч./заруб.), затем список источников. "
            "Цитируй найденные источники inline-номерами [1], [2]… в порядке появления. "
            "Не выдумывай факты, которых нет в результатах поиска.",
            system="Ты научный аналитик горно-металлургического R&D. Пиши структурировано, с цитатами [n].",
            max_tokens=1800,
        )
        report = content or reasoning
    except Exception as exc:
        _log.warning("gap_research.synth_failed", error=str(exc)[:200])
        report = f"(синтез отчёта недоступен: {type(exc).__name__})\n\nНайдено источников: {len(sources)}."

    return {"question": question, "report": report, "sources": sources, "queries": qs}
