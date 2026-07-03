"""Contradiction severity classifier (§15.4).

Классификатор серьёзности материализованного узла ``:Contradiction`` — pure-python
labeller that assigns a 4-level severity **label** ('critical'/'high'/'medium'/'low')
to a contradiction *по величине* ``relative_diff`` *и критичности свойства* (§15.4).

This is deliberately **distinct** from ``contradiction_detector``'s CI-gap severity
*float*: here we fold three ingredients into one human-facing label —

- ``relative_diff`` — the normalized magnitude of divergence in ``[0, 1]``;
- ``property_criticality`` — how important the disagreeing property is (a weight in
  ``[0, 1]``, looked up per property name, default ``0.5``);
- ``overlap`` — whether the two confidence intervals overlap. Overlapping CIs mean
  the sources may agree within uncertainty, so the label is *capped at 'low'* even
  when ``relative_diff`` is large (пересекающиеся CI → не критично).

The score is ``clamp01(relative_diff * (0.5 + 0.5 * criticality))`` so a maximally
critical property preserves the full ``relative_diff`` while a zero-criticality one
halves it. The module is pure and side-effect free — it never touches the graph
store; a caller reads the ``:Contradiction`` props via ``get_node()`` first and
passes a plain dict in. Results are a frozen dataclass exposing ``as_dict()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "ContradictionSeverity",
    "CRITICALITY",
    "classify_contradiction",
    "property_criticality",
]

# §15.4 default per-property criticality weights. ``'default'`` is the fallback for
# any unknown property. Overridable via the ``criticality_table`` argument below.
CRITICALITY: dict[str, float] = {"default": 0.5}

# Label thresholds on the folded score, strongest first (§15.4).
_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.6, "critical"),
    (0.4, "high"),
    (0.2, "medium"),
    (0.0, "low"),
)


@dataclass(frozen=True)
class ContradictionSeverity:
    """Severity verdict for one ``:Contradiction`` (§15.4).

    ``label`` is one of ``critical`` / ``high`` / ``medium`` / ``low``; ``score`` is
    the folded magnitude in ``[0, 1]``; ``relative_diff`` and ``criticality`` echo
    the inputs used, for auditability (аудит происхождения оценки).
    """

    label: str
    score: float
    relative_diff: float
    criticality: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score": self.score,
            "relative_diff": self.relative_diff,
            "criticality": self.criticality,
        }


def _clamp01(value: float) -> float:
    """Clamp ``value`` into the closed interval ``[0, 1]``."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _as_float(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to ``float`` (``bool`` / non-numeric / ``None`` → default)."""
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def property_criticality(property_name: Any, table: dict[str, float] | None = None) -> float:
    """Look up the criticality weight for ``property_name`` (§15.4).

    Falls back to ``table['default']`` (or the module ``CRITICALITY['default']``) when
    the property is unknown or the name is not a usable string. The result is clamped
    to ``[0, 1]`` (критичность свойства как вес в диапазоне единицы).
    """
    source = table if table is not None else CRITICALITY
    default = _as_float(source.get("default", CRITICALITY["default"]), 0.5)
    if not isinstance(property_name, str):
        return _clamp01(default)
    return _clamp01(_as_float(source.get(property_name, default), default))


def _label_for(score: float) -> str:
    """Map a folded ``score`` in ``[0, 1]`` to its severity label (§15.4)."""
    for threshold, label in _THRESHOLDS:
        if score >= threshold:
            return label
    return "low"


def classify_contradiction(
    c: dict[str, Any],
    *,
    criticality_table: dict[str, float] | None = None,
) -> ContradictionSeverity:
    """Label a materialized ``:Contradiction`` dict ``c`` by severity (§15.4).

    Reads ``c['relative_diff']`` (missing → ``0.0``), ``c['property']`` /
    ``c['property_name']`` for the criticality lookup, and ``c['overlap']`` (a bool):
    when the confidence intervals overlap the label is capped at ``'low'`` regardless
    of magnitude. ``score = clamp01(relative_diff * (0.5 + 0.5 * criticality))``.
    """
    relative_diff = _clamp01(_as_float(c.get("relative_diff"), 0.0))
    prop = c.get("property", c.get("property_name"))
    criticality = property_criticality(prop, criticality_table)
    score = _clamp01(relative_diff * (0.5 + 0.5 * criticality))

    # Overlapping confidence intervals cap the label at 'low' (§15.4).
    label = "low" if c.get("overlap") is True else _label_for(score)

    return ContradictionSeverity(
        label=label,
        score=score,
        relative_diff=relative_diff,
        criticality=criticality,
    )
