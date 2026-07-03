"""Ranked gap list — materials by uncovered target-property fraction (§15.5).

``coverage_matrix`` (coverage_matrix.py) builds a material × property grid of
cells, but nothing ranks *materials* by how much of the target-property set is
still unclosed. This module adds that "ranked gap list" (§15.5).

Given a flat list of matrix cells (each carrying ``material_id`` / ``material``
/ ``property`` / ``measured_count``) and the target-property set of interest,
:func:`rank_material_coverage` returns one :class:`MaterialCoverage` per
material, sorted *worst-first* (наименьшее покрытие первым): ascending
coverage ratio, breaking ties by descending count of uncovered properties.

A target property counts as *covered* for a material iff at least one cell for
that (material, property) pair has ``measured_count > 0``. Cells naming a
property outside ``target_properties`` are ignored (не входят в целевой набор).

Read-only: this module never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialCoverage:
    """Target-property coverage for one material (§15.5 ranked gap list).

    ``coverage_ratio`` = ``covered`` / ``target_total`` rounded to 4 decimals;
    ``uncovered_properties`` are the still-unclosed targets, sorted ascending.
    """

    material_id: str
    material: str
    target_total: int
    covered: int
    uncovered: int
    coverage_ratio: float
    uncovered_properties: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "material_id": self.material_id,
            "material": self.material,
            "target_total": self.target_total,
            "covered": self.covered,
            "uncovered": self.uncovered,
            "coverage_ratio": self.coverage_ratio,
            "uncovered_properties": self.uncovered_properties,
        }


def rank_material_coverage(
    cells: list[dict],
    target_properties: list[str],
) -> list[MaterialCoverage]:
    """Rank materials by fraction of *unclosed* target properties (§15.5).

    Each cell must carry ``material_id`` / ``material`` / ``property`` /
    ``measured_count``. A target property is *covered* for a material iff some
    cell for that pair has ``measured_count > 0``; cells for properties outside
    ``target_properties`` are ignored. Results are sorted worst-first
    (ascending ``coverage_ratio``, tie-break descending ``uncovered``).
    """
    targets = sorted(set(target_properties))
    target_total = len(targets)
    target_set = set(targets)

    # material_id -> display name (last non-empty wins) and covered property set.
    names: dict[str, str] = {}
    covered_by_material: dict[str, set[str]] = {}

    for cell in cells:
        material_id = cell["material_id"]
        covered_by_material.setdefault(material_id, set())
        name = cell.get("material", "")
        if name or material_id not in names:
            names[material_id] = name
        prop = cell["property"]
        if prop not in target_set:
            continue  # свойство вне целевого набора — игнорируем
        if int(cell["measured_count"]) > 0:
            covered_by_material[material_id].add(prop)

    result: list[MaterialCoverage] = []
    for material_id, covered_props in covered_by_material.items():
        covered = len(covered_props)
        uncovered_props = tuple(p for p in targets if p not in covered_props)
        uncovered = len(uncovered_props)
        ratio = round(covered / target_total, 4) if target_total else 0.0
        result.append(
            MaterialCoverage(
                material_id=material_id,
                material=names.get(material_id, ""),
                target_total=target_total,
                covered=covered,
                uncovered=uncovered,
                coverage_ratio=ratio,
                uncovered_properties=uncovered_props,
            )
        )

    result.sort(key=lambda mc: (mc.coverage_ratio, -mc.uncovered))
    return result
