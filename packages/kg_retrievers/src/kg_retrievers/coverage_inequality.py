"""Coverage inequality / concentration metrics (§25.5).

Pure-python concentration analysis of a coverage matrix. Given a flat list of
*cells* — mappings carrying a ``material``, a ``property`` and an
``evidence_count`` — :func:`coverage_inequality` aggregates the evidence per
material and per property and summarises how *unequally* that evidence is
distributed via the Gini coefficient.

Неравенство покрытия: концентрация свидетельств по материалам и свойствам.
Коэффициент Джини близок к 0 при равномерном покрытии и растёт по мере того,
как свидетельства концентрируются на немногих материалах/свойствах.

The Gini coefficient uses the sorted-index formula::

    G = (2 * Σ i·x_i) / (n · Σ x) - (n + 1) / n

where ``x`` is sorted ascending and ``i`` is the 1-based rank. It degenerates
to ``0.0`` for empty, single-element or all-zero vectors. All results are
carried in a frozen dataclass exposing :meth:`~CoverageInequality.as_dict`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

# A coverage cell: material / property / evidence_count (свидетельства).
Cell = dict[str, object]


def gini(values: list[float]) -> float:
    """Gini coefficient of ``values`` via the sorted-index formula (§25.5).

    Коэффициент Джини: 0.0 для пустого/единичного/полностью нулевого вектора.
    Otherwise ``(2·Σ i·x_i)/(n·Σ x) - (n+1)/n`` with ``x`` sorted ascending and
    ``i`` a 1-based rank. The result lies in ``[0.0, 1.0]`` for non-negative
    inputs.
    """
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    if n <= 1:
        return 0.0
    total = sum(ordered)
    if total == 0.0:
        return 0.0
    weighted = sum(i * x for i, x in enumerate(ordered, start=1))
    return (2.0 * weighted) / (n * total) - (n + 1) / n


@dataclass(frozen=True)
class CoverageInequality:
    """Concentration summary of a coverage matrix (§25.5).

    - ``gini_material`` — Gini of per-material evidence totals;
    - ``gini_property`` — Gini of per-property evidence totals;
    - ``n_materials`` / ``n_properties`` — distinct material / property keys;
    - ``most_covered_material`` — material with the highest evidence total
      (``None`` when there are no materials);
    - ``least_covered_material`` — material with the lowest evidence total
      (``None`` when there are no materials).

    Сводка неравенства покрытия по материалам и свойствам.
    """

    gini_material: float
    gini_property: float
    n_materials: int
    n_properties: int
    most_covered_material: str | None
    least_covered_material: str | None

    def as_dict(self) -> dict[str, object]:
        """JSON-ready mapping of all six fields (§25.5)."""
        return {
            "gini_material": self.gini_material,
            "gini_property": self.gini_property,
            "n_materials": self.n_materials,
            "n_properties": self.n_properties,
            "most_covered_material": self.most_covered_material,
            "least_covered_material": self.least_covered_material,
        }


def _evidence_of(cell: Cell) -> float:
    """Non-negative ``evidence_count`` of ``cell`` (missing → 0.0) (§25.5)."""
    raw = cell.get("evidence_count", 0)
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0.0 else 0.0


def coverage_inequality(cells: list[Cell]) -> CoverageInequality:
    """Aggregate ``cells`` into a :class:`CoverageInequality` (§25.5).

    Свидетельства (``evidence_count``) суммируются по каждому материалу и
    каждому свойству; затем считается коэффициент Джини для обоих распределений.
    Materials are ranked by total evidence to pick the most / least covered;
    ties are broken by material key for deterministic output.
    """
    per_material: dict[str, float] = defaultdict(float)
    per_property: dict[str, float] = defaultdict(float)
    for cell in cells:
        material = cell.get("material")
        prop = cell.get("property")
        evidence = _evidence_of(cell)
        if material is not None:
            per_material[str(material)] += evidence
        if prop is not None:
            per_property[str(prop)] += evidence

    most: str | None = None
    least: str | None = None
    if per_material:
        # Rank by (evidence, key) so ties resolve deterministically by key.
        most = max(per_material, key=lambda k: (per_material[k], k))
        least = min(per_material, key=lambda k: (per_material[k], k))

    return CoverageInequality(
        gini_material=gini(list(per_material.values())),
        gini_property=gini(list(per_property.values())),
        n_materials=len(per_material),
        n_properties=len(per_property),
        most_covered_material=most,
        least_covered_material=least,
    )
