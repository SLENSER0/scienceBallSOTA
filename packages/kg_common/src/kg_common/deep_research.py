"""Deep-research planner for scientific article discovery (§5 / library).

An OSS-only, offline-capable adaptation of **langchain-ai/open_deep_research** (MIT,
vendored at ``third_party/open_deep_research``). We mirror its pipeline structure —

    clarify_with_user → write_research_brief → supervisor(ConductResearch topics)
    → researcher(search) → final_report

— but replace its LLM+paid-web-search researcher (Tavily) with our scientific
**source catalog** (:mod:`kg_common.research_sources`): each research topic fans out
into ready-to-open per-source search links. The plan is what a human (or an
authorised fetcher) then acts on — this module orchestrates the *search*, it never
scrapes or downloads. Decomposition uses the project's OSS LLM when a key is
configured, else a deterministic fallback keeps it fully offline (§7.5 OSS-only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kg_common.research_sources import RESEARCH_SOURCES, search_url

_STOP = {
    "и",
    "в",
    "на",
    "по",
    "для",
    "с",
    "the",
    "a",
    "of",
    "in",
    "for",
    "and",
    "to",
    "как",
    "что",
    "при",
    "или",
    "how",
    "what",
    "which",
    "с помощью",
}


@dataclass(frozen=True)
class SourceQuery:
    """A single source × sub-question search link."""

    source_id: str
    source_name: str
    access: str
    query: str
    url: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "access": self.access,
            "query": self.query,
            "url": self.url,
        }


@dataclass(frozen=True)
class SubQuestion:
    """A focused sub-question plus its per-source search links."""

    text: str
    links: list[SourceQuery] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"text": self.text, "links": [link.as_dict() for link in self.links]}


@dataclass(frozen=True)
class Clarification:
    """open_deep_research ``ClarifyWithUser`` — is the question specific enough?"""

    need_clarification: bool
    question: str = ""
    verification: str = ""

    def as_dict(self) -> dict:
        return {
            "need_clarification": self.need_clarification,
            "question": self.question,
            "verification": self.verification,
        }


@dataclass(frozen=True)
class ResearchPlan:
    """A decomposed research plan: brief + sub-questions × source links (as_dict/JSON)."""

    question: str
    research_brief: str = ""
    sub_questions: list[SubQuestion] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    clarification: Clarification | None = None

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "research_brief": self.research_brief,
            "keywords": list(self.keywords),
            "clarification": self.clarification.as_dict() if self.clarification else None,
            "sub_questions": [sq.as_dict() for sq in self.sub_questions],
        }


def clarify_question(question: str) -> Clarification:
    """ODR ``clarify_with_user`` stage: flag a too-vague question (offline heuristic).

    A question is under-specified when it is very short or names no salient term;
    then we suggest a clarifying question rather than researching a fuzzy topic.
    """
    kws = extract_keywords(question)
    words = question.split()
    if len(words) < 2 or not kws:
        return Clarification(
            need_clarification=True,
            question="Уточните материал/процесс/показатель — например «удаление сульфатов "
            "из шахтных вод обратным осмосом».",
            verification="Вопрос слишком общий для литературного поиска.",
        )
    return Clarification(need_clarification=False, verification="Тема достаточно конкретна.")


def research_brief(question: str, keywords: list[str]) -> str:
    """ODR ``write_research_brief`` stage: a concise brief guiding the search."""
    focus = ", ".join(keywords[:5]) or question.strip()
    return (
        f"Найти научные источники по теме: {question.strip()}. "
        f"Ключевые аспекты: {focus}. Приоритет — рецензируемые статьи и патенты "
        "с числовыми результатами и указанием условий процесса."
    )


def extract_keywords(question: str, *, limit: int = 8) -> list[str]:
    """Salient terms of a research question (RU/EN, dedup, stopwords dropped)."""
    toks = re.findall(r"[0-9a-zA-Zа-яёА-ЯЁ][\w\-]{2,}", question.lower())
    out: list[str] = []
    for t in toks:
        if t not in _STOP and t not in out:
            out.append(t)
    return out[:limit]


def _fallback_subquestions(question: str, keywords: list[str]) -> list[str]:
    """Deterministic sub-question expansion when no LLM is available."""
    q = question.strip().rstrip("?")
    subs = [question.strip()]
    # Angle the search: methods, parameters, comparison, industrial practice.
    angles = [
        ("методы и технологии", "methods and technologies"),
        ("параметры и условия процесса", "process parameters and conditions"),
        ("промышленная практика и кейсы", "industrial practice and case studies"),
    ]
    head = " ".join(keywords[:4]) or q
    for ru, en in angles:
        subs.append(f"{head} — {ru} / {en}")
    return subs[:4]


def build_plan(
    question: str, *, source_ids: list[str] | None = None, use_llm: bool = False
) -> ResearchPlan:
    """Decompose ``question`` and build per-source search links for each sub-question.

    ``source_ids`` limits which catalog sources to include (default: all). ``use_llm``
    asks the OSS model to decompose; on any failure it falls back to the deterministic
    expansion, so the planner always returns a usable plan.
    """
    keywords = extract_keywords(question)
    sub_texts = _llm_subquestions(question) if use_llm else None
    if not sub_texts:
        sub_texts = _fallback_subquestions(question, keywords)

    active = [s for s in RESEARCH_SOURCES if source_ids is None or s.id in source_ids]
    sub_questions: list[SubQuestion] = []
    for text in sub_texts:
        links = []
        for src in active:
            url = search_url(src.id, text)
            if url:
                links.append(SourceQuery(src.id, src.name, src.access, text, url))
        sub_questions.append(SubQuestion(text=text, links=links))
    return ResearchPlan(question=question.strip(), sub_questions=sub_questions, keywords=keywords)


def _llm_subquestions(question: str) -> list[str] | None:
    """Ask the OSS LLM to split the question into 3-5 focused sub-questions.

    Returns ``None`` on any error (no key, network, parse) so callers fall back.
    """
    try:
        from kg_common import get_settings

        s = get_settings()
        if not s.llm_api_key.get_secret_value():
            return None
        from kg_common.llm import chat_completion  # type: ignore[attr-defined]

        prompt = (
            "Разбей научный вопрос на 3-5 узких под-вопросов для литературного поиска. "
            "Верни по одному под-вопросу на строку, без нумерации.\n\nВопрос: " + question
        )
        text = chat_completion(prompt, model=s.llm_model_fast)
        subs = [ln.strip("-• \t") for ln in text.splitlines() if ln.strip()]
        return subs[:5] or None
    except Exception:
        return None
