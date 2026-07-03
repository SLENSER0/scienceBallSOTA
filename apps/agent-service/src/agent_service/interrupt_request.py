"""§13.21 human-in-the-loop interrupt request / запрос на прерывание с участием человека.

Pure-python, deterministic value object describing a point where the agent must pause
and ask a human to disambiguate an entity, confirm a claim, or approve a query before it
runs. Nothing here touches the graph store, so the module stays unit-testable without a
seeded Kuzu database (свойства узлов Kuzu не являются колонками запроса / node props are
not queryable columns — irrelevant here, no store access).

Surface:

* :class:`InterruptRequest` — frozen dataclass ``(type, question, options, context)`` with
  :meth:`~InterruptRequest.as_dict` for JSON-safe serialisation and ``type`` validation.
* :func:`clarify_entity` — build a ``clarify_entity`` request from candidate dicts.
* :func:`validate_resume` — check a human-supplied resume value against the offered options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

# Allowed interrupt kinds (разрешённые типы прерываний / allowed interrupt kinds).
ALLOWED_TYPES: frozenset[str] = frozenset({"clarify_entity", "confirm_claim", "approve_query"})

# Immutable empty mapping — default context (неизменяемый пустой контекст / frozen empty).
_EMPTY_CONTEXT: MappingProxyType[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class InterruptRequest:
    """A pause point where the agent asks a human / точка запроса к человеку.

    ``type`` must be one of :data:`ALLOWED_TYPES`; ``options`` enumerates the acceptable
    resume values (пустой кортеж — свободный ответ / empty tuple means free-form).
    """

    type: str
    question: str
    options: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=lambda: dict(_EMPTY_CONTEXT))

    def __post_init__(self) -> None:
        """Validate ``type`` against :data:`ALLOWED_TYPES` / проверить тип."""
        if self.type not in ALLOWED_TYPES:
            allowed = ", ".join(sorted(ALLOWED_TYPES))
            raise ValueError(
                f"unknown interrupt type / неизвестный тип прерывания: {self.type!r} "
                f"(allowed / допустимо: {allowed})"
            )

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe projection / JSON-совместимая проекция.

        ``options`` becomes a ``list``; ``context`` round-trips unchanged.
        """
        return {
            "type": self.type,
            "question": self.question,
            "options": list(self.options),
            "context": dict(self.context),
        }


def clarify_entity(question: str, candidates: list[dict[str, Any]]) -> InterruptRequest:
    """Build a ``clarify_entity`` request / собрать запрос на уточнение сущности.

    Options are drawn from each candidate's ``canonical_id`` (falling back to ``label``);
    the raw candidates are preserved under ``context['candidates']``.
    """
    options = tuple(str(cand.get("canonical_id") or cand.get("label") or "") for cand in candidates)
    return InterruptRequest(
        type="clarify_entity",
        question=question,
        options=options,
        context={"candidates": candidates},
    )


def validate_resume(req: InterruptRequest, resume_value: str) -> bool:
    """True iff ``resume_value`` is acceptable / допустимо ли значение возобновления.

    Any value is accepted when ``req.options`` is empty (free-form / свободный ответ).
    """
    if not req.options:
        return True
    return resume_value in req.options
