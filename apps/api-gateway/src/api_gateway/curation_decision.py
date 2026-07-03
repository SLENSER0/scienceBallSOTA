"""Валидация тела решения ревью для ``POST /curation/review-queue/{task_id}`` (§14.14).

Эндпоинт ревью-очереди принимает решение куратора «принять / отклонить /
исправить» и превращает его в действие :class:`CurationEvent` из §12.3. Модуль
``kg_common.audit_taxonomy`` хранит лишь *словарь* глаголов кураторства и не
проверяет тело запроса — здесь живёт недостающий валидатор тела и отображение
решения в аудиторское действие. Чистый stdlib, детерминированно, без побочных
эффектов.

The review-queue endpoint takes a curator's accept/reject/correct decision and
maps it to a §12.3 :class:`CurationEvent` action. ``kg_common.audit_taxonomy``
only owns the *vocabulary* of curation verbs and never validates a request body;
this module supplies the missing body validator plus the decision→action map.
Pure stdlib, deterministic, side-effect free.

* :data:`DECISIONS` — frozen set of accepted decision verbs.
* :class:`ReviewDecision` — frozen validated decision with :meth:`as_dict`.
* :func:`parse_decision` — request-body mapping → ``ReviewDecision``.
* :func:`to_curation_action` — ``ReviewDecision`` → §12.3 curation action string.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DECISIONS",
    "ReviewDecision",
    "parse_decision",
    "to_curation_action",
]

# Допустимые решения ревью — accepted review decisions (§14.14, subset of §12.3).
DECISIONS: frozenset[str] = frozenset({"accept", "reject", "correct"})


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    """Неизменяемое проверенное решение ревью (§14.14).

    Immutable, already-validated review decision. ``decision`` is one of
    :data:`DECISIONS`; ``corrected`` carries the replacement payload for a
    ``"correct"`` decision (``None`` otherwise); ``reason`` is the curator's
    non-blank justification recorded in the audit trail (§12.3).
    """

    decision: str
    corrected: dict[str, Any] | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление решения — ``{decision, corrected, reason}`` (§14.14).

        Возвращает все три поля дословно (включая ``corrected=None``), чтобы
        форма была стабильной и пригодной для записи в аудит.

        Returns all three fields verbatim (including ``corrected=None``) so the
        wire form is stable and audit-ready.
        """
        return {
            "decision": self.decision,
            "corrected": self.corrected,
            "reason": self.reason,
        }


def parse_decision(body: Mapping[str, Any]) -> ReviewDecision:
    """Разобрать и проверить тело решения ревью (§14.14).

    Правила: ``decision`` обязан входить в :data:`DECISIONS`; при
    ``decision == "correct"`` требуется непустой словарь ``corrected``; ``reason``
    не может быть пустым/пробельным.

    Validate a review-decision body: ``decision`` must be in :data:`DECISIONS`; a
    ``"correct"`` decision requires a non-empty ``corrected`` mapping; ``reason``
    must be non-blank.

    :raises ValueError: при неизвестном ``decision``, отсутствии ``corrected`` для
        ``correct`` или пустом ``reason`` / on unknown ``decision``, missing
        ``corrected`` for a correction, or blank ``reason``.
    """
    decision = body.get("decision")
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}, got {decision!r}")

    reason = body.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-blank string")

    corrected_raw = body.get("corrected")
    if decision == "correct":
        if not isinstance(corrected_raw, Mapping) or not corrected_raw:
            raise ValueError("a 'correct' decision requires a non-empty 'corrected' payload")
        corrected: dict[str, Any] | None = dict(corrected_raw)
    else:
        corrected = None

    return ReviewDecision(decision=decision, corrected=corrected, reason=reason)


def to_curation_action(d: ReviewDecision) -> str:
    """Отобразить решение в действие :class:`CurationEvent` §12.3 (§14.14).

    ``accept`` и ``reject`` переносятся дословно; ``correct`` отображается в
    ``"correct"``. Результат гарантированно лежит в
    ``kg_common.audit_taxonomy.CURATION_ACTIONS``.

    Map a decision to its §12.3 :class:`CurationEvent` action. ``accept`` and
    ``reject`` pass through unchanged; ``correct`` maps to ``"correct"``. The
    result is guaranteed to be a member of ``CURATION_ACTIONS``.
    """
    return d.decision
