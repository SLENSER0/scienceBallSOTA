"""Ingestion stage state machine (§5.6/§5.10).

Models the linear ingestion pipeline lifecycle ``queued → parsing → storing →
chunking → done`` as an explicit, hand-checkable state machine. ``jobs.py`` only
persists a coarse job status; this module builds the fine-grained ladder used to
drive progress reporting and to guard illegal transitions. A stage may advance
exactly one step forward along :data:`STAGES`, or (from any non-terminal stage)
jump to a terminal failure/cancellation. ``progress_for`` maps each stage to a
monotonically increasing fraction in ``[0.0, 1.0]``.

Конечный автомат стадий приёма (§5.6/§5.10): очередь → разбор → сохранение →
разбиение → готово. Разрешён шаг вперёд на одну стадию либо переход в терминальное
состояние (ошибка/отмена). ``progress_for`` даёт монотонно растущую долю прогресса.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STAGES: tuple[str, ...] = ("queued", "parsing", "storing", "chunking", "done")
"""Ordered pipeline stages (§5.10). Прогрессия стадий приёма."""

TERMINAL_STAGES: frozenset[str] = frozenset({"done", "failed", "cancelled"})
"""Stages from which no further transition is allowed. Терминальные стадии."""

# Non-terminal failure/cancellation sinks reachable from any active stage.
_ABORT_STAGES: frozenset[str] = frozenset({"failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class StageState:
    """Immutable snapshot of one ingestion job's stage (§5.10).

    Неизменяемый снимок текущей стадии одной задачи приёма: стадия, прогресс,
    необязательное сообщение об ошибке.
    """

    stage: str
    progress: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict. Сериализация в обычный словарь."""
        return {"stage": self.stage, "progress": self.progress, "error": self.error}


def _is_terminal(stage: str) -> bool:
    return stage in TERMINAL_STAGES


def can_transition(cur: str, nxt: str) -> bool:
    """Return whether ``cur → nxt`` is a legal stage transition (§5.10).

    Legal moves: one step forward along :data:`STAGES`, or from any non-terminal
    stage to ``failed``/``cancelled``. No move leaves a terminal stage.

    Допустимо: шаг вперёд по :data:`STAGES` либо переход из нетерминальной стадии
    в ``failed``/``cancelled``.
    """
    if cur not in STAGES and cur not in TERMINAL_STAGES:
        return False
    if _is_terminal(cur):
        return False
    if nxt in _ABORT_STAGES:
        return True
    if cur not in STAGES or nxt not in STAGES:
        return False
    return STAGES.index(nxt) == STAGES.index(cur) + 1


def progress_for(stage: str) -> float:
    """Map ``stage`` to a fraction in ``[0.0, 1.0]`` (§5.10).

    ``queued`` is ``0.0`` and ``done`` is ``1.0``, increasing monotonically between.
    Terminal ``failed``/``cancelled`` report ``0.0`` (progress is undefined once
    aborted).

    Доля прогресса стадии: ``queued`` → 0.0, ``done`` → 1.0, монотонно между ними.
    """
    if stage in _ABORT_STAGES:
        return 0.0
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage!r}")
    return STAGES.index(stage) / (len(STAGES) - 1)


def advance(state: StageState, nxt: str, error: str | None = None) -> StageState:
    """Advance ``state`` to ``nxt``, returning a new :class:`StageState` (§5.10).

    Raises :class:`ValueError` if the transition is illegal. When ``nxt`` is a
    failure/cancellation the ``error`` string is preserved; otherwise ``error`` is
    cleared and ``progress`` is recomputed from :func:`progress_for`.

    Переход к стадии ``nxt`` с проверкой допустимости; при ошибке сохраняется текст.
    """
    if not can_transition(state.stage, nxt):
        raise ValueError(f"illegal transition: {state.stage!r} -> {nxt!r}")
    if nxt in _ABORT_STAGES:
        return StageState(stage=nxt, progress=state.progress, error=error)
    return StageState(stage=nxt, progress=progress_for(nxt), error=None)
