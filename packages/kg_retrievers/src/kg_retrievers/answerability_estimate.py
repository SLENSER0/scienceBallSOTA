"""§25.15 — retriever-side answerability estimate over coverage cells.

Given a set of coverage *cells* (each either present/COVERED or absent with a
``confidence_of_absence``), decide whether the retriever should answer, abstain,
or explicitly report an absence — *before* handing anything to the generator.

Каждая ячейка (cell) — это запрошенный факт: либо он присутствует (status
``COVERED``), либо отсутствует, и тогда у него есть уверенность в отсутствии
(``confidence_of_absence`` в ``[0, 1]``). Мы считаем долю присутствующих ячеек
и минимальную уверенность отсутствия по пустым ячейкам:

* ``present_fraction >= answer_at``           -> ``answer`` (достаточно данных);
* иначе ``no_data_confidence < abstain_below`` -> ``abstain`` (слишком неуверенно);
* иначе                                        -> ``report_absence`` (уверенный пробел).

``no_data_confidence`` — минимум ``confidence_of_absence`` по отсутствующим
ячейкам (``1.0``, если отсутствующих нет): самая слабая уверенность отсутствия
задаёт, можем ли мы честно заявить о пробеле.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# -- cell status ------------------------------------------------------------
COVERED = "COVERED"  # ячейка присутствует в графе / present cell

# -- decisions --------------------------------------------------------------
ANSWER = "answer"  # достаточно присутствующих данных, чтобы отвечать
ABSTAIN = "abstain"  # мало данных и низкая уверенность отсутствия -> молчим
REPORT_ABSENCE = "report_absence"  # мало данных, но уверенный пробел -> сообщаем

# -- default thresholds -----------------------------------------------------
ANSWER_AT = 0.5  # present_fraction >= this -> answer
ABSTAIN_BELOW = 0.3  # no_data_confidence < this (and not answer) -> abstain


@dataclass(frozen=True)
class AnswerabilityEstimate:
    """Оценка отвечаемости по набору ячеек покрытия / answerability over cells.

    ``present_fraction`` — доля присутствующих ячеек (``n_present / n_cells``,
    или ``0.0`` при пустом входе). ``no_data_confidence`` — минимальная уверенность
    отсутствия по пустым ячейкам (``1.0``, если пустых нет). ``decision`` — одно из
    ``answer`` / ``abstain`` / ``report_absence``.
    """

    n_cells: int
    n_present: int
    present_fraction: float
    no_data_confidence: float
    decision: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_cells": self.n_cells,
            "n_present": self.n_present,
            "present_fraction": self.present_fraction,
            "no_data_confidence": self.no_data_confidence,
            "decision": self.decision,
        }


def _is_present(cell: dict[str, Any]) -> bool:
    """True, если ячейка присутствует (status == ``COVERED``) / cell is present."""
    return str(cell.get("status", "")).upper() == COVERED


def _absence_confidence(cell: dict[str, Any]) -> float:
    """Read a cell's ``confidence_of_absence`` as a float, defaulting to ``1.0``.

    Отсутствие поля трактуем как полную уверенность отсутствия (``1.0``): без
    сигнала об обратном пустая ячейка считается настоящим пробелом.
    """
    value = cell.get("confidence_of_absence", 1.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def estimate_answerability(
    cells: list[dict],
    *,
    answer_at: float = ANSWER_AT,
    abstain_below: float = ABSTAIN_BELOW,
) -> AnswerabilityEstimate:
    """Estimate answerability over ``cells`` -> :class:`AnswerabilityEstimate`.

    Присутствующей считается ячейка со status ``COVERED``. Доля присутствия
    ``present_fraction = n_present / n_cells`` (``0.0`` при пустом входе).
    ``no_data_confidence`` — минимум ``confidence_of_absence`` по отсутствующим
    ячейкам (``1.0``, если отсутствующих нет). Решение: ``answer``, когда
    ``present_fraction >= answer_at``; иначе ``abstain``, когда
    ``no_data_confidence < abstain_below``; иначе ``report_absence``. Пустой
    вход (``cells == []``) всегда даёт ``abstain`` — сообщать не о чем.
    """
    n_cells = len(cells)
    present = [c for c in cells if _is_present(c)]
    absent = [c for c in cells if not _is_present(c)]
    n_present = len(present)

    present_fraction = n_present / n_cells if n_cells else 0.0
    no_data_confidence = min(_absence_confidence(c) for c in absent) if absent else 1.0

    if not n_cells:
        # Пустой вход: сообщать не о чем -> воздерживаемся (§25.15).
        decision = ABSTAIN
    elif present_fraction >= answer_at:
        decision = ANSWER
    elif no_data_confidence < abstain_below:
        decision = ABSTAIN
    else:
        decision = REPORT_ABSENCE

    return AnswerabilityEstimate(
        n_cells=n_cells,
        n_present=n_present,
        present_fraction=present_fraction,
        no_data_confidence=no_data_confidence,
        decision=decision,
    )
