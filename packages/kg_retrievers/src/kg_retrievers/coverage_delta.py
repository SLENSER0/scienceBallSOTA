"""Coverage-delta between two coverage snapshots (§15.16).

Pure-python comparison of two *coverage snapshots* — mappings of a material
(материал) to a boolean ``covered`` flag — with no dependency on the graph
store. Given a ``before`` and an ``after`` snapshot, :func:`coverage_delta`
reports which materials became covered, which lost coverage, the net change and
the percentage change relative to the ``before`` coverage count.

Дельта покрытия: сравнение двух снимков покрытия (материал → покрыт/нет).

A material missing from a snapshot is treated as *not covered* (``False``), so
the two snapshots need not share the same key set. The result is a frozen
dataclass exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass

# Snapshot type: material id / name -> covered flag (покрыт / нет).
CoverageSnapshot = dict[str, bool]


def _covered_keys(snapshot: CoverageSnapshot) -> set[str]:
    """Material keys flagged covered (truthy) in ``snapshot`` (§15.16)."""
    return {material for material, covered in snapshot.items() if covered}


@dataclass(frozen=True)
class CoverageDelta:
    """Difference between two coverage snapshots (§15.16).

    - ``added_covered`` — materials covered in *after* but not in *before*;
    - ``lost_covered`` — materials covered in *before* but not in *after*;
    - ``net`` — ``len(added_covered) - len(lost_covered)`` (signed);
    - ``pct_change`` — percentage change of the covered count relative to the
      *before* count. When *before* has no covered materials it is ``0.0`` if
      *after* has none either, else ``100.0``.

    Both tuples are sorted for deterministic output.
    """

    added_covered: tuple[str, ...]
    lost_covered: tuple[str, ...]
    net: int
    pct_change: float

    def as_dict(self) -> dict:
        return {
            "added_covered": list(self.added_covered),
            "lost_covered": list(self.lost_covered),
            "net": self.net,
            "pct_change": self.pct_change,
        }


def coverage_delta(before: CoverageSnapshot, after: CoverageSnapshot) -> CoverageDelta:
    """Compare two coverage snapshots (material → covered) (§15.16).

    ``added_covered`` and ``lost_covered`` are sorted tuples of material keys;
    ``net`` is the signed change in the covered count (equal to
    ``len(added_covered) - len(lost_covered)``); ``pct_change`` is that change as
    a percentage of the *before* covered count, rounded to two decimals.
    """
    before_covered = _covered_keys(before)
    after_covered = _covered_keys(after)

    added = tuple(sorted(after_covered - before_covered))
    lost = tuple(sorted(before_covered - after_covered))
    net = len(added) - len(lost)

    before_count = len(before_covered)
    if before_count == 0:
        pct_change = 0.0 if len(after_covered) == 0 else 100.0
    else:
        pct_change = round(net / before_count * 100, 2)

    return CoverageDelta(
        added_covered=added,
        lost_covered=lost,
        net=net,
        pct_change=pct_change,
    )
