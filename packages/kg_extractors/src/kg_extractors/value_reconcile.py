"""Cross-layer numeric value reconciliation (§6.13).

Согласование расхождений числовых значений между слоями извлечения.

``extraction_confidence`` boosts a fact's confidence when extraction layers
agree, but agreement alone does not settle *which number* to keep when the
rule layer and the LLM layer disagree. This module reconciles conflicting
numeric values from several layers by relative tolerance and layer priority,
and flags a review conflict when the values genuinely diverge.

Per §6.13 «rule-факты для чисел предпочтительнее LLM при конфликте» — when
values conflict the highest-priority layer wins, and ``rule`` outranks ``llm``
outranks ``ml`` by default.

- :func:`reconcile_numeric` — collapse ``[(layer, value, unit), ...]`` to a
  single :class:`Reconciled`: the winner is the candidate from the
  highest-priority layer; ``conflict`` is true iff any value falls outside
  ``rel_tol`` of the maximum; ``spread`` is ``max - min``.

Pure python — no external dependency. Deterministic and hand-checkable.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default relative tolerance and layer precedence (§6.13). `rule` first: rule
# facts for numbers are preferred over LLM on conflict.
DEFAULT_REL_TOL: float = 0.02
DEFAULT_LAYER_PRIORITY: tuple[str, ...] = ("rule", "llm", "ml")

# Rounding used to tame binary-float noise on the reported spread.
_ROUND = 9


@dataclass(frozen=True)
class Reconciled:
    """A reconciled numeric fact across extraction layers (§6.13).

    ``value``/``unit`` are taken from the winning candidate. ``chosen_layer`` is
    that candidate's layer. ``conflict`` is true when the layers disagree beyond
    tolerance and the fact needs review. ``spread`` is ``max - min`` of the
    candidate values (``0.0`` for a single candidate).
    """

    value: float
    unit: str | None
    chosen_layer: str
    conflict: bool
    spread: float

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "unit": self.unit,
            "chosen_layer": self.chosen_layer,
            "conflict": self.conflict,
            "spread": self.spread,
        }


def _priority_index(layer: str, layer_priority: tuple[str, ...]) -> int:
    """Rank a layer by ``layer_priority`` order; unknown layers rank last."""
    try:
        return layer_priority.index(layer)
    except ValueError:
        return len(layer_priority)


def reconcile_numeric(
    candidates: list[tuple[str, float, str | None]],
    rel_tol: float = DEFAULT_REL_TOL,
    layer_priority: tuple[str, ...] = DEFAULT_LAYER_PRIORITY,
) -> Reconciled:
    """Reconcile per-layer numeric candidates into one :class:`Reconciled` (§6.13).

    ``candidates`` is a list of ``(layer, value, unit)``. Values within
    ``rel_tol`` of the maximum value are treated as agreeing (``conflict``
    False); otherwise the fact is flagged for review (``conflict`` True). The
    winner — regardless of conflict — is the candidate from the highest-priority
    layer, so rule facts win over LLM (§6.13). ``spread`` is ``max - min``.

    Согласование числовых кандидатов слоёв: победитель — самый приоритетный слой,
    конфликт — если значения расходятся сильнее ``rel_tol``.
    """
    if not candidates:
        raise ValueError("reconcile_numeric requires at least one candidate")

    values = [value for _, value, _ in candidates]
    hi = max(values)
    lo = min(values)
    spread = round(hi - lo, _ROUND)

    # Agreement: every value must sit within rel_tol of the maximum (§6.13).
    tol = abs(hi) * rel_tol
    conflict = any(abs(hi - value) > tol for value in values)

    # Winner: the highest-priority layer; ties keep first-seen order (stable).
    layer, value, unit = min(candidates, key=lambda c: _priority_index(c[0], layer_priority))
    return Reconciled(
        value=value,
        unit=unit,
        chosen_layer=layer,
        conflict=conflict,
        spread=spread,
    )
