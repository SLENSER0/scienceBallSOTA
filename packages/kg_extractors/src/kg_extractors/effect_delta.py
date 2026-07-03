"""Baseline→value quantitative effect delta (§6.6).

:mod:`kg_extractors.measurement_linker` records a ``baseline_value`` and a
cue-word ``effect_direction`` (increase/decrease/no_change), but it never
computes the actual numeric change nor checks whether that change agrees with
the direction the text *states*. This module closes that gap: given a
``baseline`` and a measured ``value`` it derives the absolute change, the
percentage change, the direction implied by the numbers, and — when the text
also asserted a direction — whether the two are consistent.

Даёт количественную дельту эффекта: абсолютное и процентное изменение,
производное направление (рост/спад/без изменений) и проверку согласованности
с заявленным в тексте направлением (§6.6).

``abs_change`` is the *absolute* (i.e. non-percentage) change ``value -
baseline`` and keeps its sign; ``pct_change`` is the signed relative change in
percent, or ``None`` when the baseline is zero (deltа не определена). The
derived direction uses ``no_change_tol`` as the dead-band around zero, so a
negligible numeric drift still reads as ``no_change``.

Pure python — no dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Derived / stated direction vocabulary (§6.6) — mirrors measurement_linker.
EFFECT_INCREASE = "increase"
EFFECT_DECREASE = "decrease"
EFFECT_NO_CHANGE = "no_change"

# Synonyms accepted for a *stated* direction so a raw cue word still compares
# cleanly against the derived direction (rise→increase, drop→decrease …).
_STATED_ALIASES: dict[str, str] = {
    "increase": EFFECT_INCREASE,
    "increased": EFFECT_INCREASE,
    "up": EFFECT_INCREASE,
    "rise": EFFECT_INCREASE,
    "rose": EFFECT_INCREASE,
    "grew": EFFECT_INCREASE,
    "higher": EFFECT_INCREASE,
    "decrease": EFFECT_DECREASE,
    "decreased": EFFECT_DECREASE,
    "down": EFFECT_DECREASE,
    "drop": EFFECT_DECREASE,
    "dropped": EFFECT_DECREASE,
    "fell": EFFECT_DECREASE,
    "reduced": EFFECT_DECREASE,
    "lower": EFFECT_DECREASE,
    "no_change": EFFECT_NO_CHANGE,
    "no change": EFFECT_NO_CHANGE,
    "unchanged": EFFECT_NO_CHANGE,
    "same": EFFECT_NO_CHANGE,
}


def _normalize_stated(stated: str) -> str | None:
    """Map a stated-direction surface form to the controlled set, else ``None``."""
    key = stated.strip().lower()
    return _STATED_ALIASES.get(key)


@dataclass(frozen=True)
class EffectDelta:
    """Quantitative baseline→value effect + stated-direction consistency (§6.6)."""

    baseline: float
    value: float
    abs_change: float
    pct_change: float | None
    direction: str
    direction_stated: str | None
    consistent: bool

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain dict (``consistent`` stays a real ``bool``)."""
        out = asdict(self)
        out["consistent"] = bool(self.consistent)
        return out


def compute_effect_delta(
    baseline: float,
    value: float,
    stated_direction: str | None = None,
    no_change_tol: float = 1e-9,
) -> EffectDelta:
    """Compute the effect delta from ``baseline`` to ``value`` (§6.6).

    Направление выводится из знака ``value - baseline`` с учётом мёртвой зоны
    ``no_change_tol``; ``consistent`` = False, когда заявленное направление
    противоречит выведенному. ``pct_change`` = None при нулевом базисе.
    """
    abs_change = float(value) - float(baseline)

    if abs(abs_change) <= no_change_tol:
        direction = EFFECT_NO_CHANGE
    elif abs_change > 0:
        direction = EFFECT_INCREASE
    else:
        direction = EFFECT_DECREASE

    # baseline == 0 → деление на ноль, процентное изменение не определено.
    pct_change: float | None = None if baseline == 0 else abs_change / baseline * 100.0

    # Consistency: only a *contradicting* stated direction is inconsistent; an
    # absent or unrecognizable stated direction is treated as consistent.
    consistent = True
    if stated_direction is not None:
        normalized = _normalize_stated(stated_direction)
        if normalized is not None and normalized != direction:
            consistent = False

    return EffectDelta(
        baseline=float(baseline),
        value=float(value),
        abs_change=abs_change,
        pct_change=pct_change,
        direction=direction,
        direction_stated=stated_direction,
        consistent=consistent,
    )
