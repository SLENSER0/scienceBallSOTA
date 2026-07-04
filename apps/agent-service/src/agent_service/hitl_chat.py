"""§13.21 HITL clarification for the chat agent / уточнение сущности в диалоге.

The chat agent normally resolves a mention to a graph node with best-effort and
answers straight away. This module supplies the *pause-and-ask* half of §13.21:
before answering it scans the question for a **critical** domain entity whose top
graph candidates are near-ties (ambiguity that blocks the answer) and, if found,
builds the :class:`~agent_service.interrupt_request.InterruptRequest` the UI needs
to ask the human which entity was meant. After the human replies, the chosen
canonical id is folded back into the question so the resumed run resolves the
entity unambiguously.

Everything here composes already-built, unit-tested pieces — nothing is
re-implemented:

* :func:`kg_extractors.query_parser.parse_query` — detect domain-entity mentions.
* :func:`agent_service.tools_ext.resolve_entities` — graph-node candidates per
  mention (reuses :class:`~kg_retrievers.alias_index.AliasIndex`).
* :func:`agent_service.resolution_clarify.decide_resolution` — the §7.5 Node 3
  clarify gate (critical **and** top-two near-tie).
* :func:`agent_service.interrupt_request.clarify_entity` /
  :func:`~agent_service.interrupt_request.validate_resume` — request DTO + resume
  validation.

The only impure dependency is the graph ``store`` handed in by the caller; the
decision logic itself is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_service.interrupt_request import InterruptRequest, clarify_entity, validate_resume
from agent_service.resolution_clarify import decide_resolution
from agent_service.tools_ext import resolve_entities
from kg_extractors.query_parser import parse_query

# Confidence gap below which the top two candidates count as a near-tie (§7.5).
DEFAULT_MARGIN: float = 0.15
# How many graph candidates to keep per mention when asking the human.
DEFAULT_LIMIT: int = 5


@dataclass(frozen=True)
class ClarifyOutcome:
    """A pending §13.21 clarification for one ambiguous critical mention.

    ``mention`` is the surface entity that needs disambiguation; ``request`` is the
    :class:`InterruptRequest` to surface in the UI (its ``context['candidates']``
    carries human-readable names). ``as_dict`` is the wire shape the router returns.
    """

    mention: str
    request: InterruptRequest

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{mention, request}`` (request already JSON-safe)."""
        return {"mention": self.mention, "request": self.request.as_dict()}


def _candidate_view(raw: dict[str, Any]) -> dict[str, Any]:
    """Adapt a :func:`resolve_entities` candidate to the clarify-gate shape.

    ``resolve_entities`` yields ``{entity_id, score, name, label}``; the clarify gate
    and :func:`clarify_entity` want ``{canonical_id, confidence, label, name}``.
    """
    return {
        "canonical_id": raw.get("entity_id"),
        "confidence": float(raw.get("score") or 0.0),
        "label": raw.get("label"),
        "name": raw.get("name") or raw.get("entity_id"),
    }


def _mentions(query: str) -> list[str]:
    """Domain-entity surface forms detected in ``query`` (RU/EN), de-duplicated."""
    intent = parse_query(query)
    seen: dict[str, None] = {}
    for entry in intent.entities:
        for surface in (entry.canonical_ru, entry.canonical_en):
            if surface and surface not in seen:
                seen[surface] = None
    return list(seen)


def find_clarification(
    store: Any,
    query: str,
    *,
    margin: float = DEFAULT_MARGIN,
    limit: int = DEFAULT_LIMIT,
) -> ClarifyOutcome | None:
    """Return the first blocking §13.21 clarification for ``query`` or ``None``.

    For each detected domain-entity mention we pull its ranked graph candidates and
    run the §7.5 Node 3 gate: a mention is treated as **critical** (every domain
    entity is load-bearing for a mining-KG answer), so a clarification fires only
    when the top-two candidates are a near-tie (``gap < margin``). The first such
    mention wins; the human is asked once, the rest fall back to best-effort. When
    no mention is ambiguous the function returns ``None`` and the caller answers
    directly.

    По каждому упоминанию сущности: если топ-2 кандидата неразличимы —
    выставляем запрос на уточнение; иначе продолжаем best-guess (§13.21).
    """
    for mention in _mentions(query):
        resolved = resolve_entities(store, mentions=[mention], limit=limit)
        rows = resolved.get("mentions") or []
        if not rows:
            continue
        raw_candidates = list(rows[0].get("candidates") or [])
        if len(raw_candidates) < 2:
            continue  # nothing to disambiguate
        candidates = [_candidate_view(c) for c in raw_candidates]
        decision = decide_resolution(candidates, critical=True, margin=margin)
        if not decision.should_clarify:
            continue
        question = (
            f"«{mention}» может относиться к нескольким сущностям — уточните, "
            f"какую имели в виду. / '{mention}' is ambiguous — which entity did you mean?"
        )
        request = clarify_entity(question, candidates)
        return ClarifyOutcome(mention=mention, request=request)
    return None


def resume_query(query: str, outcome: ClarifyOutcome, resume_value: str) -> str:
    """Fold the human's chosen entity back into ``query`` for the resumed run.

    ``resume_value`` must be one of the offered options (validated via
    :func:`validate_resume`; a :class:`ValueError` is raised otherwise). The chosen
    candidate's human-readable name is appended as an explicit disambiguation hint so
    the re-parsed question resolves to exactly that entity, and the raw canonical id
    is included for traceability.

    Возвращает уточнённый запрос, в который вшит выбор пользователя (§13.21).
    """
    if not validate_resume(outcome.request, resume_value):
        offered = ", ".join(outcome.request.options)
        raise ValueError(
            f"resume value {resume_value!r} is not an offered option / "
            f"недопустимый выбор (допустимо: {offered})"
        )
    candidates = outcome.request.context.get("candidates") or []
    chosen = next(
        (c for c in candidates if c.get("canonical_id") == resume_value),
        None,
    )
    name = (chosen or {}).get("name") or resume_value
    # Explicit hint that re-parsing (parse_query) will pick up deterministically.
    return f"{query} [уточнено / clarified: {name} ({resume_value})]"
