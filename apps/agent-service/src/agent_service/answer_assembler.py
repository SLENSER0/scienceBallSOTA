"""§13.14 сборка итогового AnswerPayload / assemble the final AnswerPayload dict.

Pure-python, deterministic projection: take the already-prepared parts of an
answer (текст ответа, цитаты, граф, пробелы, противоречия, уверенность, модели)
and fold them into a single JSON-ready dict whose keys are the camelCase aliases
of :class:`kg_common.AnswerPayload` (§5.3). Nothing here touches the graph store
or an LLM, so the module stays unit-testable without a seeded Kuzu database.

Each part is normalised to a plain value: pydantic models (:class:`kg_common.Citation`,
:class:`kg_common.GraphResponse`) are dumped ``by_alias=True`` to camelCase dicts,
frozen dataclasses via their ``as_dict()``, mappings shallow-copied, everything else
passed through untouched. Missing optional parts collapse to the DTO defaults —
empty lists for citations/gaps/contradictions/usedModels, ``None`` for graph and
confidence — so the returned dict always carries the same seven keys.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


def _to_payload(part: Any) -> Any:
    """Normalise one part to a JSON-ready value (модель/датакласс/словарь → dict).

    A pydantic model is dumped ``by_alias=True`` (camelCase, recursively); a frozen
    dataclass with :meth:`as_dict` is expanded; a mapping is shallow-copied so the
    caller's object is never aliased; anything else is returned unchanged. ``None``
    passes straight through (граф отсутствует / graph absent).
    """
    if part is None:
        return None
    model_dump = getattr(part, "model_dump", None)
    if callable(model_dump):
        return model_dump(by_alias=True)
    as_dict = getattr(part, "as_dict", None)
    if callable(as_dict):
        return as_dict()
    if isinstance(part, Mapping):
        return dict(part)
    return part


@dataclass(frozen=True)
class AssembledAnswer:
    """The seven normalised parts of an answer, ready to project to §5.3 keys.

    Field names stay snake_case for Python; :meth:`as_dict` renders the camelCase
    ``AnswerPayload`` aliases. ``graph``/``confidence`` are optional (``None`` when
    absent); the three list fields default to empty via :func:`assemble_answer`.
    """

    answer_markdown: str
    citations: list[Any]
    graph: dict[str, Any] | None
    gaps: list[Any]
    contradictions: list[Any]
    confidence: float | None
    used_models: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the camelCase ``AnswerPayload`` subset (§5.3)."""
        return {
            "answerMarkdown": self.answer_markdown,
            "citations": self.citations,
            "graph": self.graph,
            "gaps": self.gaps,
            "contradictions": self.contradictions,
            "confidence": self.confidence,
            "usedModels": self.used_models,
        }


def assemble_answer(
    *,
    answer_markdown: str,
    citations: Iterable[Any],
    graph: Any = None,
    gaps: Iterable[Any] | None = None,
    contradictions: Iterable[Any] | None = None,
    confidence: float | None = None,
    used_models: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Fold answer parts into a §5.3 ``AnswerPayload`` camelCase dict (§13.14).

    ``answer_markdown`` (пустая строка допустима / empty string tolerated) and
    ``citations`` are required; the rest are optional. Missing ``gaps``,
    ``contradictions`` and ``used_models`` become empty lists; missing ``graph`` and
    ``confidence`` become ``None``. ``confidence`` is passed through verbatim (без
    клампинга / no clamping). Every part is normalised by :func:`_to_payload`, so
    the result is JSON-ready and validates against :class:`kg_common.AnswerPayload`.
    """
    return AssembledAnswer(
        answer_markdown=answer_markdown,
        citations=[_to_payload(c) for c in citations],
        graph=_to_payload(graph),
        gaps=[_to_payload(g) for g in gaps] if gaps is not None else [],
        contradictions=(
            [_to_payload(c) for c in contradictions] if contradictions is not None else []
        ),
        confidence=confidence,
        used_models=list(used_models) if used_models is not None else [],
    ).as_dict()
