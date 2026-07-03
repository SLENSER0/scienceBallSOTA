"""LangGraph agent state schema (§13.11 / §7.5).

Pure-python, dependency-light state container that flows through the QA
LangGraph (§7.5 preprocess → parse → retrieve → synthesize → verify). Unlike the
runtime ``TypedDict`` used to compile the graph in :mod:`agent_service.agent`,
this module gives a **frozen, hand-checkable snapshot** of that state for tests,
logging, checkpointing and retry accounting (``attempts``).

Единое состояние агента / single agent state — the fields mirror the workflow
nodes:

* ``question`` — нормализованный вопрос / the (normalized) user question.
* ``intent`` — результат классификации намерения (§13.8) as a plain dict.
* ``preprocessed`` — вывод препроцессора (§13.7) as a plain dict.
* ``retrieval`` — извлечённый контекст / retrieved context (passages, graph).
* ``answer`` — итоговый markdown-ответ / final grounded markdown answer.
* ``citations`` — цитаты / citation records (immutable tuple).
* ``gaps`` — пробелы в знаниях / knowledge-gap notes (immutable tuple).
* ``verifier_report`` — отчёт верификатора (§13.16) as a plain dict.
* ``attempts`` — счётчик попыток / retry counter incremented via ``merge_state``.

Design notes
------------
* ``frozen=True`` — nodes never mutate state in place; they return a small dict
  of overrides that :func:`merge_state` folds into a **new** ``AgentState``
  (LangGraph's reducer contract). Mutable ``dict`` fields default to ``None`` and
  the list-like ``citations`` / ``gaps`` are stored as immutable tuples.
* ``as_dict`` emits JSON-friendly values (tuples → lists); ``from_dict`` coerces
  them back, so ``from_dict(s.as_dict()) == s`` round-trips exactly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

__all__ = ["AgentState", "empty_state", "merge_state"]


@dataclass(frozen=True)
class AgentState:
    """Frozen snapshot of the LangGraph QA state (§13.11).

    All fields carry defaults so a partial state (e.g. only ``question``) is
    always constructible; mutable containers use ``None`` / empty-tuple defaults
    to keep the dataclass frozen-safe.
    """

    question: str = ""
    intent: dict[str, Any] | None = None
    preprocessed: dict[str, Any] | None = None
    retrieval: dict[str, Any] | None = None
    answer: str | None = None
    citations: tuple[Any, ...] = ()
    gaps: tuple[Any, ...] = ()
    verifier_report: dict[str, Any] | None = None
    attempts: int = 0

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly structured view (tuples → lists) for state/logging (§7.3)."""
        return {
            "question": self.question,
            "intent": self.intent,
            "preprocessed": self.preprocessed,
            "retrieval": self.retrieval,
            "answer": self.answer,
            "citations": list(self.citations),
            "gaps": list(self.gaps),
            "verifier_report": self.verifier_report,
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AgentState:
        """Rebuild from a (possibly partial) mapping; missing keys take defaults.

        Coerces ``citations`` / ``gaps`` back to tuples and ``attempts`` to
        ``int`` so :meth:`as_dict` round-trips exactly. Unknown keys are ignored
        (forward-compatible with older/newer checkpoints).
        """
        d = dict(data)
        return cls(
            question=d.get("question", "") or "",
            intent=d.get("intent"),
            preprocessed=d.get("preprocessed"),
            retrieval=d.get("retrieval"),
            answer=d.get("answer"),
            citations=tuple(d.get("citations") or ()),
            gaps=tuple(d.get("gaps") or ()),
            verifier_report=d.get("verifier_report"),
            attempts=int(d.get("attempts") or 0),
        )


_FIELD_NAMES: frozenset[str] = frozenset(f.name for f in fields(AgentState))


def empty_state(question: str) -> AgentState:
    """Fresh state for ``question`` with every other field at its default (§13.11)."""
    return AgentState(question=question)


def merge_state(a: AgentState, b: Mapping[str, Any] | AgentState) -> AgentState:
    """Shallow-merge overrides ``b`` onto ``a``, returning a **new** ``AgentState``.

    ``b`` is either a mapping of field overrides (as LangGraph nodes return) or a
    full :class:`AgentState` (its fields win). ``a`` is never mutated. Unknown
    override keys raise ``ValueError`` so a typo can't be silently dropped.
    """
    updates = b.as_dict() if isinstance(b, AgentState) else dict(b)
    unknown = set(updates) - _FIELD_NAMES
    if unknown:
        raise ValueError(f"merge_state: unknown state key(s): {sorted(unknown)}")
    merged = a.as_dict()
    merged.update(updates)
    return AgentState.from_dict(merged)
