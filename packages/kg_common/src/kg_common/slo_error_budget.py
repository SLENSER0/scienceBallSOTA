"""SLO error-budget & burn-rate calculator — бюджет ошибок SLO (§23.16).

An SLO fixes a *target* success ratio (say ``0.99`` — «три девятки без одной»).
The complement ``1 - target`` is the **error budget**: the fraction of requests
that may fail before the objective is breached. ``latency_stats`` only reports
percentiles; nothing here tracks how much of that budget a window of traffic has
already burned. This module fills that gap.

From the good/total request counts of an observation window it derives:

* ``observed_success``          — ``good / total`` («наблюдаемая успешность»);
* ``budget_total``              — ``1 - target``, the allowed error fraction;
* ``budget_consumed``           — the observed error fraction ``bad / total``;
* ``budget_remaining_fraction`` — ``1 - burn_rate`` clamped to ``>= 0.0`` (share
  of the budget still unspent, «сколько бюджета осталось»);
* ``burn_rate``                 — ``observed_error_rate / budget_total``: how many
  times faster than «exactly on budget» the errors are accruing.

Alerting («тревоги», §23.16 multi-window burn-rate policy):

* ``ok``       — ``burn_rate < 1`` (spending slower than the budget allows);
* ``warning``  — ``burn_rate >= 1`` (on or over budget for this window);
* ``critical`` — ``burn_rate >= 14.4`` (fast-burn: the whole monthly budget would
  be gone in about an hour — «быстрое прогорание»).

Public API:

* :data:`FAST_BURN` — the ``14.4`` fast-burn threshold.
* :class:`ErrorBudget` — frozen verdict with :meth:`ErrorBudget.as_dict`.
* :func:`evaluate` — build an :class:`ErrorBudget` from ``target/good/total``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FAST_BURN",
    "ErrorBudget",
    "evaluate",
]

#: Fast-burn multiple — при таком burn_rate месячный бюджет сгорает за ~час.
FAST_BURN: float = 14.4


@dataclass(frozen=True, slots=True)
class ErrorBudget:
    """Immutable error-budget verdict for one window — вердикт по окну (§23.16).

    ``target`` is the SLO success ratio in ``(0, 1)``; ``total``/``bad`` are the
    request counts; ``observed_success`` is ``good / total``. ``budget_total`` is
    the allowed error fraction ``1 - target``; ``budget_consumed`` is the observed
    error fraction; ``budget_remaining_fraction`` is the unspent share of the
    budget, clamped to ``>= 0.0``. ``burn_rate`` is the fast/slow multiple and
    ``alert`` is one of ``ok``/``warning``/``critical``.
    """

    target: float
    total: int
    bad: int
    observed_success: float
    budget_total: float
    budget_consumed: float
    budget_remaining_fraction: float
    burn_rate: float
    alert: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — строка карточки бюджета ошибок (§23.16)."""
        return {
            "target": self.target,
            "total": self.total,
            "bad": self.bad,
            "observed_success": self.observed_success,
            "budget_total": self.budget_total,
            "budget_consumed": self.budget_consumed,
            "budget_remaining_fraction": self.budget_remaining_fraction,
            "burn_rate": self.burn_rate,
            "alert": self.alert,
        }


def evaluate(target: float, good: int, total: int) -> ErrorBudget:
    """Compute the error budget & burn rate for a window — посчитать бюджет (§23.16).

    ``target`` must lie strictly in ``(0, 1)`` and ``total`` must be positive;
    ``good`` is clamped into ``[0, total]`` before use. Raises :class:`ValueError`
    on an out-of-range ``target`` or a non-positive ``total``.
    """
    if not 0.0 < target < 1.0:
        raise ValueError(f"target must be in (0, 1), got {target!r}")
    if total <= 0:
        raise ValueError(f"total must be positive, got {total!r}")

    good = max(0, min(good, total))
    bad = total - good
    # Round to tame float noise so the SLO thresholds compare exactly (§23.16).
    observed_success = round(good / total, 9)
    observed_error_rate = round(bad / total, 9)
    budget_total = round(1.0 - target, 9)
    burn_rate = round(observed_error_rate / budget_total, 9)
    budget_remaining_fraction = round(max(0.0, 1.0 - burn_rate), 9)

    if burn_rate >= FAST_BURN:
        alert = "critical"
    elif burn_rate >= 1.0:
        alert = "warning"
    else:
        alert = "ok"

    return ErrorBudget(
        target=target,
        total=total,
        bad=bad,
        observed_success=observed_success,
        budget_total=budget_total,
        budget_consumed=observed_error_rate,
        budget_remaining_fraction=budget_remaining_fraction,
        burn_rate=burn_rate,
        alert=alert,
    )
