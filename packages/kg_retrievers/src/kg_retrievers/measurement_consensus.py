"""Value reconciliation / contradiction consensus (§15.4).

Согласование значений — pure-python computation of a single reconciled
best-estimate across a *group* of conflicting, already-normalized Measurement
dicts (§15.4). Where :mod:`contradiction_detector` only picks a single
``likely_correct`` id for a **pair**, this module answers a different question:
given N measurements of the *same* property in the *same* unit, what is the most
defensible point value, and which members look like outliers?

Each member is a plain dict with the keys ``value_normalized`` /
``normalized_unit`` / ``confidence`` / ``evidence_strength`` / ``id``. Every
member is weighted by ``max(confidence, 0.0)``; the reconciled ``estimate`` is
the confidence-weighted mean, so low-confidence disagreement is dampened
(маловероятные значения почти не влияют на оценку). The ``anchor`` is the
highest-weight member and outliers are members whose relative deviation from the
estimate exceeds ``outlier_tol``.

The module is pure and side-effect free — it never touches the graph store.
Results are frozen dataclasses exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

__all__ = [
    "ConsensusEstimate",
    "consensus_estimate",
]

# A normalized Measurement dict; the reconciliation keys are read defensively.
Measurement = dict[str, Any]


@dataclass(frozen=True)
class ConsensusEstimate:
    """Reconciled best-estimate across a conflicting measurement group (§15.4).

    Сводная оценка по группе противоречивых измерений. ``estimate`` is the
    confidence-weighted mean of the members' ``value_normalized``; ``weighted``
    is ``True`` when at least one member carried positive confidence (otherwise
    the estimate degrades to a plain arithmetic mean). ``relative_spread`` is
    ``(max - min) / max(|v|)`` over the raw member values — a scale-free measure
    of disagreement. ``anchor_measurement_id`` names the highest-weight member and
    ``outlier_ids`` lists members whose ``|v - estimate| / |estimate|`` exceeds
    the caller's tolerance.
    """

    subject_key: str
    property_name: str
    unit: str
    estimate: float
    weighted: bool
    member_count: int
    relative_spread: float
    anchor_measurement_id: str
    outlier_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of all nine fields (§15.4)."""
        data = asdict(self)
        data["outlier_ids"] = list(self.outlier_ids)
        return data


def _as_float(value: Any) -> float | None:
    """Best-effort float coercion; ``None`` on missing/malformed input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def consensus_estimate(
    measurements: list[Measurement],
    *,
    min_members: int = 2,
    outlier_tol: float = 0.5,
    subject_key: str = "",
    property_name: str = "",
) -> ConsensusEstimate | None:
    """Reconcile a conflicting measurement group into one estimate (§15.4).

    Сводит группу измерений к единой оценке. Returns ``None`` unless at least
    ``min_members`` members carry a usable ``value_normalized`` **and** every
    member shares one ``normalized_unit`` — a unit mismatch is not reconcilable.

    Each member is weighted by ``max(confidence, 0.0)``; ``estimate`` is the
    weighted mean (plain mean if all weights are zero). ``relative_spread`` is
    ``(max - min) / max(|v|)`` and outliers are members whose relative deviation
    from the estimate exceeds ``outlier_tol``. The anchor is the highest-weight
    member (ties broken by the earliest occurrence).
    """
    values: list[float] = []
    weights: list[float] = []
    ids: list[str] = []
    units: set[str] = set()

    for member in measurements:
        value = _as_float(member.get("value_normalized"))
        if value is None:
            continue
        unit = str(member.get("normalized_unit", ""))
        units.add(unit)
        weight = _as_float(member.get("confidence"))
        weight = max(weight, 0.0) if weight is not None else 0.0
        values.append(value)
        weights.append(weight)
        ids.append(str(member.get("id", "")))

    if len(values) < min_members:
        return None
    if len(units) != 1:
        return None

    total_weight = sum(weights)
    weighted = total_weight > 0.0
    if weighted:
        estimate = sum(v * w for v, w in zip(values, weights, strict=True)) / total_weight
    else:
        estimate = sum(values) / len(values)

    v_max = max(values)
    v_min = min(values)
    scale = max(abs(v) for v in values)
    relative_spread = (v_max - v_min) / scale if scale > 0.0 else 0.0

    # Anchor = highest-weight member; earliest occurrence wins on a tie.
    anchor_idx = max(range(len(ids)), key=lambda i: weights[i])
    anchor_id = ids[anchor_idx]

    # Outliers: relative deviation from the estimate above tolerance. When the
    # estimate collapses to zero we cannot form a relative deviation, so no
    # member is flagged (нельзя оценить относительное отклонение от нуля).
    outlier_ids: list[str] = []
    if estimate != 0.0:
        denom = abs(estimate)
        for value, member_id in zip(values, ids, strict=True):
            if abs(value - estimate) / denom > outlier_tol:
                outlier_ids.append(member_id)

    return ConsensusEstimate(
        subject_key=subject_key,
        property_name=property_name,
        unit=next(iter(units)),
        estimate=estimate,
        weighted=weighted,
        member_count=len(values),
        relative_spread=relative_spread,
        anchor_measurement_id=anchor_id,
        outlier_ids=tuple(outlier_ids),
    )
