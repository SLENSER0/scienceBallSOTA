"""Cross-scale hardness consistency check (§7.3, ASTM E140).

:mod:`kg_common.units.hardness` converts a *single* hardness value between
scales, but nothing checks whether **several** hardness measurements reported
for one sample (possibly on mixed scales — HV/HB/HRC) mutually agree. This
module converts every measurement to Vickers (HV) via the existing
:func:`convert_hardness`, then flags the group as consistent when the spread of
convertible HV values stays within a tolerance.

RU: Проверка согласованности твёрдости, измеренной в разных шкалах для одного
образца. Каждое измерение приводится к HV; группа считается согласованной,
если разброс (max-min) не превышает допуск ``tol_hv``.
EN: See the English description above.

Pure Python, no I/O. Builds **on** ``hardness`` (reuses ``convert_hardness``).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from kg_common.units.hardness import convert_hardness


@dataclass(frozen=True)
class HardnessConsistency:
    """Result of a cross-scale hardness consistency check.

    RU: Результат проверки согласованности твёрдости в разных шкалах.
    EN: Result of a cross-scale hardness consistency check.
    """

    values_hv: tuple[float, ...]
    spread_hv: float
    consistent: bool
    outlier_indices: tuple[int, ...]
    unconvertible: tuple[int, ...]

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view (tuples → lists) for JSON/serialisation."""
        return {
            "values_hv": list(self.values_hv),
            "spread_hv": self.spread_hv,
            "consistent": self.consistent,
            "outlier_indices": list(self.outlier_indices),
            "unconvertible": list(self.unconvertible),
        }


def check_hardness_consistency(
    measurements: list[tuple[float, str]],
    tol_hv: float = 25.0,
) -> HardnessConsistency:
    """Check whether mixed-scale hardness measurements mutually agree.

    Each ``(value, scale)`` is converted to HV via :func:`convert_hardness`.
    Indices whose scale cannot be converted are recorded in ``unconvertible``.
    ``spread_hv`` is ``max-min`` over the convertible HV values; the group is
    ``consistent`` when ``spread_hv <= tol_hv``. When inconsistent,
    ``outlier_indices`` holds the original index/indices whose HV lies farthest
    from the HV median.

    RU: Приводит каждое измерение к HV, вычисляет разброс и отмечает выбросы.
    EN: See above.
    """
    hv_by_index: list[tuple[int, float]] = []
    unconvertible: list[int] = []
    for i, (value, scale) in enumerate(measurements):
        try:
            hv_by_index.append((i, convert_hardness(value, scale, "HV").value))
        except (ValueError, KeyError):
            unconvertible.append(i)

    values_hv = tuple(hv for _, hv in hv_by_index)
    if not values_hv:
        # Nothing convertible → vacuously consistent, zero spread.
        return HardnessConsistency(
            values_hv=(),
            spread_hv=0.0,
            consistent=True,
            outlier_indices=(),
            unconvertible=tuple(unconvertible),
        )

    spread_hv = max(values_hv) - min(values_hv)
    consistent = spread_hv <= tol_hv

    outlier_indices: tuple[int, ...] = ()
    if not consistent:
        med = median(values_hv)
        max_dist = max(abs(hv - med) for _, hv in hv_by_index)
        outlier_indices = tuple(i for i, hv in hv_by_index if abs(hv - med) == max_dist)

    return HardnessConsistency(
        values_hv=values_hv,
        spread_hv=round(spread_hv, 6),
        consistent=consistent,
        outlier_indices=outlier_indices,
        unconvertible=tuple(unconvertible),
    )
