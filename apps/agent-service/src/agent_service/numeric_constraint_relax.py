"""§13.10 ослабление числовых tolerance при повторе верификатора / tolerance relaxation.

The §13.10 planner, when re-called on a **verifier-retry**, must expand the plan not
only by *appending strategies* (that is :func:`agent_service.query_plan.expand_plan`)
but also by **ослабление tolerance** — loosening the numeric tolerances so that a
near-miss constraint (e.g. ``temperature_c`` within a few degrees) can now match. The
existing ``expand_plan`` only merges ``retrieval_strategy`` and never touches
``numeric_constraints``; this module supplies the missing tolerance-widening step.

:func:`relax` takes the plan's ``numeric_constraints`` and a retry ``attempt`` counter
and returns a frozen :class:`RelaxedConstraints`. For every numeric constraint key that
maps (via :data:`TOLERANCE_KEYS`) to a tolerance key, the base tolerance is multiplied
by ``factor ** attempt`` — so ``attempt == 0`` is a no-op (``factor**0 == 1``) and each
further retry widens the window geometrically. The **constraint values themselves are
never changed** (мы расширяем окно допуска, а не сами ограничения); only the tolerances
grow. Keys absent from the constraints are ignored, and the input dict is copied, never
mutated. Nothing here touches the graph store or an LLM — fully offline unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

# Числовое ограничение -> его ключ tolerance / numeric-constraint key -> tolerance key (§13.10).
TOLERANCE_KEYS: dict[str, str] = {
    "temperature_c": "temperature_tolerance",  # °C window around a target temperature
    "time_h": "time_tolerance",  # hours window around a target duration
}

# Базовые допуски по умолчанию / default base tolerances, one per §13.10 tolerance key.
DEFAULT_TOLERANCES: dict[str, float] = {
    "temperature_tolerance": 5.0,  # ±5 °C default window
    "time_tolerance": 0.5,  # ±0.5 h default window
}


@dataclass(frozen=True)
class RelaxedConstraints:
    """Result of one §13.10 tolerance-relaxation step (frozen, JSON-serialisable).

    Fields
    ------
    constraints
        The numeric constraints, **unchanged** in value — a copy of the input
        (числовые ограничения без изменений, только копия).
    tolerances
        The widened tolerances keyed by their §13.10 tolerance key, i.e. the base
        tolerance scaled by ``factor ** attempt`` (расширенные допуски).
    attempt
        The verifier-retry attempt number this relaxation was computed for
        (номер попытки повтора).
    widened
        The constraint keys that actually got a widened tolerance, in insertion
        order — only keys present in ``constraints`` with a mapped tolerance
        (какие ключи были расширены).
    """

    constraints: dict[str, object]
    tolerances: dict[str, float]
    attempt: int
    widened: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialise to a JSON-ready dict (list, not tuple) for state/logging (§7.3)."""
        return {
            "constraints": dict(self.constraints),
            "tolerances": dict(self.tolerances),
            "attempt": self.attempt,
            "widened": list(self.widened),
        }


def relax(
    constraints: dict[str, object],
    attempt: int,
    *,
    factor: float = 1.5,
    base: dict[str, float] | None = None,
) -> RelaxedConstraints:
    """Widen numeric tolerances for a §13.10 verifier-retry, leaving values unchanged.

    For each key in ``constraints`` that maps (via :data:`TOLERANCE_KEYS`) to a
    tolerance key, its tolerance is ``base_tolerance * factor ** attempt`` where the
    base tolerance is taken from ``base`` (per tolerance key) or, failing that, from
    :data:`DEFAULT_TOLERANCES`. At ``attempt == 0`` the scale is ``factor ** 0 == 1``,
    so tolerances equal their base (no-op relaxation). Constraint **values are never
    modified**, and the input ``constraints`` dict is copied rather than mutated.

    Parameters
    ----------
    constraints
        The plan's numeric constraints, e.g. ``{"temperature_c": 200}`` (ограничения).
    attempt
        The verifier-retry attempt number; ``0`` leaves tolerances at their base.
    factor
        Geometric widening factor per attempt (коэффициент расширения, default 1.5).
    base
        Optional per-tolerance-key base overrides; missing keys fall back to
        :data:`DEFAULT_TOLERANCES`.

    Returns
    -------
    RelaxedConstraints
        The copied constraints, the widened tolerances, ``attempt`` and the tuple of
        widened constraint keys (in insertion order).
    """
    base_tolerances = DEFAULT_TOLERANCES if base is None else {**DEFAULT_TOLERANCES, **base}
    scale = factor**attempt
    tolerances: dict[str, float] = {}
    widened: list[str] = []
    for key in constraints:  # preserve insertion order of the constraints dict
        tol_key = TOLERANCE_KEYS.get(key)
        if tol_key is None:  # no mapped tolerance — ключ без допуска игнорируется
            continue
        tolerances[tol_key] = base_tolerances[tol_key] * scale
        widened.append(key)
    return RelaxedConstraints(
        constraints=dict(constraints),  # copy: input must never be mutated
        tolerances=tolerances,
        attempt=attempt,
        widened=tuple(widened),
    )
