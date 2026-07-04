"""Agentic Technology Advisor — многоагентная рекомендация технологий.

Instead of a single retrieval pass, this runs a fan-out of reasoning agents over the
graph: for a user's constraints (material + geography + numeric limits) it retrieves
candidate technologies, then spawns ONE evaluation agent PER candidate (in parallel)
that reasons — grounded in that candidate's measurements, limitations and evidence —
about how well it fits, what supports it, its limitations and its knowledge gaps.
A final synthesis agent ranks them and writes the recommendation, flagging any
contradictions in the underlying evidence.

Everything runs on OSS models via OpenRouter (§7.5): per-candidate evaluation uses the
strong reasoning model (GLM-5.2), synthesis uses the fast synth model (DeepSeek-V4-Flash).
Candidate agents run concurrently (I/O-bound LLM calls) so latency ≈ the slowest one.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

from kg_common import get_logger, get_settings
from kg_extractors.query_parser import parse_query
from kg_retrievers.graph_retriever import GraphRetriever

_log = get_logger("advisor")
_MAX_CANDIDATES = 8
_MAX_WORKERS = 10  # fan out up to 10 candidate-evaluation agents at once (user-requested)


@dataclass
class AdvisorCandidate:
    id: str
    name: str
    practice_type: str
    fit_score: int  # 0..100
    verdict: str
    supports: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    n_measurements: int = 0
    relevance: int = 0  # 2=on-topic (name match), 1=same domain, 0=off-topic
    model: str | None = None


@dataclass
class AdvisorResult:
    query: str
    geography: str | None
    constraints: list[dict[str, Any]]
    candidates: list[AdvisorCandidate]
    summary: str
    contradictions: list[dict[str, Any]]
    used_models: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "geography": self.geography,
            "constraints": self.constraints,
            "candidates": [asdict(c) for c in self.candidates],
            "summary": self.summary,
            "contradictions": self.contradictions,
            "usedModels": self.used_models,
        }


_STOP = {
    "методы",
    "метод",
    "способы",
    "способ",
    "технологии",
    "для",
    "при",
    "из",
    "как",
    "какие",
    "и",
    "в",
    "на",
    "с",
    "по",
    "воды",
    "вода",
    "практика",
    "практике",
}


def _terms(text: str) -> set[str]:
    import re

    return {t for t in re.findall(r"[а-яёa-z0-9]+", text.lower()) if len(t) >= 4 and t not in _STOP}


def _query_terms(intent: Any, query: str) -> set[str]:
    """Significant surface terms the query is *about* (entities + content words)."""
    terms: set[str] = _terms(query)
    for e in intent.entities:
        for attr in ("canonical_ru", "canonical_en", "id", "name"):
            v = getattr(e, attr, None)
            if v:
                terms |= _terms(str(v))
    return terms


def _relevance_tier(sol: dict[str, Any], q_terms: set[str], intent: Any) -> int:
    """2 = candidate name matches a query term (on-topic); 1 = same domain; 0 = off-topic.

    Prevents the adversarial failure where an off-topic technology the agent itself rates
    ~10% outranks the on-topic one it can't score for lack of data (which sorted to 0).
    """
    name = f"{sol.get('name', '')} {sol.get('id', '')}"
    if _terms(name) & q_terms:
        return 2
    dom = sol.get("domain")
    if dom and dom in set(intent.domains):
        return 1
    return 0


# -- prompt building --------------------------------------------------------
def _measurements_text(sol: dict[str, Any]) -> str:
    out = []
    for m in sol.get("measurements", [])[:12]:
        val = m.get("value_normalized")
        unit = m.get("normalized_unit") or m.get("unit") or ""
        name = m.get("property_name") or m.get("name") or "показатель"
        if val is not None:
            out.append(f"{name}: {val} {unit}".strip())
    return "; ".join(out) or "нет числовых данных"


def _constraints_text(intent: Any) -> str:
    parts = []
    for c in intent.numeric_constraints:
        d = c.as_dict()
        op = d.get("operator")
        if op == "range":
            parts.append(f"{d.get('min')}–{d.get('max')} {d.get('unit', '')}".strip())
        else:
            parts.append(f"{op} {d.get('value')} {d.get('unit', '')}".strip())
    geo = (
        "отечественная"
        if "russia" in intent.practice_types
        else ("зарубежная" if "foreign" in intent.practice_types else "любая")
    )
    return f"числовые условия: {'; '.join(parts) or 'нет'} | практика: {geo}"


_EVAL_SYSTEM = (
    "Ты — инженер-технолог по горному делу и металлургии. Оцени, насколько технология "
    "подходит под условия пользователя, СТРОГО опираясь на приведённые данные. Правила: "
    "(1) НЕ выдумывай чисел; называй число «подтверждённым» только если оно явно есть в "
    "«измерениях из графа». (2) Если это generic-значение без опоры на граф — не считай его "
    "доказательством. (3) Если данных по технологии почти нет — fit_score НЕ выше 40. "
    "(4) Если технология вне темы запроса (relevance=вне темы) — fit_score НЕ выше 15. "
    'Верни JSON: {"fit_score": 0-100, "verdict": "1 фраза", '
    '"supports": ["аргументы за, только с числами из графа"], "limitations": ["ограничения"], '
    '"gaps": ["чего не хватает в данных"]}.'
)

_REL_LABEL = {2: "прямо на тему запроса", 1: "смежная область", 0: "вне темы запроса"}


def _evaluate_candidate(
    sol: dict[str, Any], query: str, constraints: str, q_terms: set[str], intent: Any
) -> AdvisorCandidate:
    """One reasoning agent per candidate technology (grounded in its graph facts)."""
    from kg_extractors.llm import get_llm

    name = sol.get("name") or sol.get("id")
    tier = _relevance_tier(sol, q_terms, intent)
    limitations = [x for x in sol.get("limitations", []) if x][:6]
    applic = [x for x in sol.get("applicability", []) if x][:6]
    meas = _measurements_text(sol)
    user = (
        f"Запрос: {query}\n{constraints}\n\n"
        f"Технология: {name}  (relevance: {_REL_LABEL[tier]})\n"
        f"Измерения из графа: {meas}\n"
        f"Область применимости: {'; '.join(applic) or 'н/д'}\n"
        f"Известные ограничения: {'; '.join(limitations) or 'н/д'}\n\n"
        "Оцени соответствие условиям."
    )
    fit, verdict, sup, lim, gaps, model = 50, "", [], limitations, [], None
    try:
        llm = get_llm()
        data = llm.complete_json(
            user, system=_EVAL_SYSTEM, model=get_settings().llm_model_synth_quality, max_tokens=1200
        )
        model = llm.used_models[-1] if llm.used_models else None
        if isinstance(data, dict):
            fit = int(max(0, min(100, data.get("fit_score", 50))))
            verdict = str(data.get("verdict", "")).strip()
            sup = [str(x) for x in data.get("supports", [])][:6]
            lim = [str(x) for x in data.get("limitations", limitations)][:6]
            gaps = [str(x) for x in data.get("gaps", [])][:6]
    except Exception as exc:  # degrade to a graph-only card, never fail the whole run
        _log.warning("advisor.eval_failed", tech=str(name)[:60], error=str(exc)[:120])
        verdict = "оценка недоступна (модель), показаны данные графа"

    return AdvisorCandidate(
        id=str(sol.get("id")),
        name=str(name),
        practice_type=str(sol.get("practice_type") or "unknown"),
        fit_score=fit,
        verdict=verdict,
        supports=sup,
        limitations=lim,
        gaps=gaps,
        n_measurements=len(sol.get("measurements", [])),
        relevance=tier,
        model=model,
    )


_SUMMARY_SYSTEM = (
    "Ты — научный консультант. По ранжированному списку технологий и их оценкам напиши "
    "краткую рекомендацию (3–5 предложений) по-русски: что выбрать под условия и почему, "
    "с оговорками. Опирайся только на предоставленные оценки."
)


def _synthesize(
    query: str, ranked: list[AdvisorCandidate], contradictions: list[dict]
) -> tuple[str, str | None]:
    from kg_extractors.llm import get_llm

    lines = [
        f"{i + 1}. {c.name} — соответствие {c.fit_score}% — {c.verdict}"
        for i, c in enumerate(ranked[:5])
    ]
    contra = f"\nПротиворечия в данных: {len(contradictions)}." if contradictions else ""
    user = f"Запрос: {query}\nОценки:\n" + "\n".join(lines) + contra
    try:
        llm = get_llm()
        text = llm.complete(
            user, system=_SUMMARY_SYSTEM, model=get_settings().llm_model_synth, max_tokens=600
        )
        return text, (llm.used_models[-1] if llm.used_models else None)
    except Exception as exc:
        _log.warning("advisor.summary_failed", error=str(exc)[:120])
        return "Рекомендация построена по оценкам соответствия (см. карточки ниже).", None


# -- orchestration ----------------------------------------------------------
def _rank_key(c: AdvisorCandidate) -> tuple[int, int]:
    # On-topic candidates ALWAYS outrank off-topic ones; then by fit (adversarial fix #1).
    return (c.relevance, c.fit_score)


def _prepare(query: str, store: Any, geography: str | None, top_k: int):  # type: ignore[no-untyped-def]
    intent = parse_query(query)
    if geography and geography != "all":
        intent.practice_types = [geography]
    retrieval = GraphRetriever(store).retrieve(intent)
    candidates = retrieval.solutions[: max(1, min(top_k, _MAX_CANDIDATES))]
    constraints = _constraints_text(intent)
    q_terms = _query_terms(intent, query)
    return intent, retrieval, candidates, constraints, q_terms


def advise(
    query: str, store: Any, *, geography: str | None = None, top_k: int = 5
) -> AdvisorResult:
    """Run the full multi-agent advisory synchronously and return the ranked result."""
    intent, retrieval, candidates, constraints, q_terms = _prepare(query, store, geography, top_k)

    evals: list[AdvisorCandidate] = []
    if candidates:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            evals = list(
                pool.map(
                    lambda c: _evaluate_candidate(c, query, constraints, q_terms, intent),
                    candidates,
                )
            )
    evals.sort(key=_rank_key, reverse=True)

    summary, sum_model = _synthesize(query, evals, retrieval.contradictions)
    used = sorted({m for c in evals if (m := c.model)} | ({sum_model} if sum_model else set()))
    return AdvisorResult(
        query=query,
        geography=geography,
        constraints=[c.as_dict() for c in intent.numeric_constraints],
        candidates=evals,
        summary=summary,
        contradictions=retrieval.contradictions[:10],
        used_models=used,
    )


def stream_advise(query: str, store: Any, *, geography: str | None = None, top_k: int = 5):  # type: ignore[no-untyped-def]
    """Generator yielding (event, data) as each candidate agent finishes — live agentic feel."""
    intent, retrieval, candidates, constraints, q_terms = _prepare(query, store, geography, top_k)
    yield "constraints", {"text": constraints, "candidates": len(candidates)}

    evals: list[AdvisorCandidate] = []
    if candidates:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = [
                pool.submit(_evaluate_candidate, c, query, constraints, q_terms, intent)
                for c in candidates
            ]
            for fut in as_completed(futures):  # stream each card the instant its agent finishes
                cand = fut.result()
                evals.append(cand)
                yield "candidate", asdict(cand)
    evals.sort(key=_rank_key, reverse=True)

    summary, sum_model = _synthesize(query, evals, retrieval.contradictions)
    yield "summary", {"text": summary}
    used = sorted({m for c in evals if (m := c.model)} | ({sum_model} if sum_model else set()))
    yield (
        "done",
        {
            "ranked": [c.id for c in evals],
            "usedModels": used,
            "contradictions": len(retrieval.contradictions),
        },
    )
