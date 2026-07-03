"""Absence-map delta over two snapshots (§25.11).

Pure-python comparison of two *absence maps* — flat lists of ``CoverageCell``-shaped
dicts, each keyed on ``(material_id, property_name)`` and carrying a ``status`` — with
no dependency on the graph store. Given a ``before`` and an ``after`` snapshot,
:func:`diff_absence_maps` joins the two lists by cell key and reports how the map of
the unknown moved: which cells became covered (``resolved``), which lost coverage
(``regressed``), which keys are brand-new or dropped, how many stayed identical, and a
full transition histogram ``{'<old>-><new>': count}``.

Дельта карты неизвестного: сравнение двух снимков покрытия (материал × свойство) по
статусам ячеек — что закрылось, что регрессировало, что появилось/исчезло.

A cell is considered *resolved* when its status moves from any non-``COVERED`` value to
``COVERED``, and *regressed* when ``COVERED`` becomes any other status. Keys present in
only one snapshot never contribute a transition — they land in ``new_cells`` (after
only) or ``dropped_cells`` (before only). The result is a frozen dataclass exposing
``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass

# Status token that marks a cell as covered by evidence (§25.11).
COVERED = "COVERED"

# A cell key: (material_id, property_name) — материал × свойство.
CellKey = tuple[str, str]


def cell_key(cell: dict) -> CellKey:
    """Key a ``CoverageCell``-shaped dict on ``(material_id, property_name)`` (§25.11).

    Missing fields default to the empty string so malformed cells still key
    deterministically rather than raising.
    """
    return (str(cell.get("material_id", "")), str(cell.get("property_name", "")))


def _status(cell: dict) -> str:
    """Status token of a cell (empty string when absent)."""
    return str(cell.get("status", ""))


@dataclass(frozen=True)
class AbsenceMapDelta:
    """Difference between two absence-map snapshots (§25.11).

    - ``n_before`` / ``n_after`` — sizes of the input cell lists;
    - ``resolved`` — keys whose status moved non-``COVERED`` → ``COVERED``;
    - ``regressed`` — keys whose status moved ``COVERED`` → non-``COVERED``;
    - ``new_cells`` — keys present only in *after*;
    - ``dropped_cells`` — keys present only in *before*;
    - ``unchanged`` — count of shared keys whose status is identical;
    - ``transitions`` — histogram ``{'<old>-><new>': count}`` over shared keys.

    All key lists are sorted for deterministic output.
    """

    n_before: int
    n_after: int
    resolved: list[CellKey]
    regressed: list[CellKey]
    new_cells: list[CellKey]
    dropped_cells: list[CellKey]
    unchanged: int
    transitions: dict[str, int]

    def as_dict(self) -> dict:
        return {
            "n_before": self.n_before,
            "n_after": self.n_after,
            "resolved": [list(k) for k in self.resolved],
            "regressed": [list(k) for k in self.regressed],
            "new_cells": [list(k) for k in self.new_cells],
            "dropped_cells": [list(k) for k in self.dropped_cells],
            "unchanged": self.unchanged,
            "transitions": dict(self.transitions),
        }


def diff_absence_maps(before: list[dict], after: list[dict]) -> AbsenceMapDelta:
    """Diff two absence maps (lists of ``CoverageCell``-shaped dicts) by key (§25.11).

    Cells are joined on :func:`cell_key`. For every key present in *both* snapshots a
    transition ``'<old>-><new>'`` is tallied; the key is ``resolved`` when the status
    moves from any non-``COVERED`` value to ``COVERED``, ``regressed`` when ``COVERED``
    becomes non-``COVERED``, and counted in ``unchanged`` when the status is identical.
    Keys unique to *after* become ``new_cells``; keys unique to *before* become
    ``dropped_cells`` — neither contributes a transition.
    """
    before_map = {cell_key(c): _status(c) for c in before}
    after_map = {cell_key(c): _status(c) for c in after}

    before_keys = set(before_map)
    after_keys = set(after_map)
    shared = before_keys & after_keys

    resolved: list[CellKey] = []
    regressed: list[CellKey] = []
    transitions: dict[str, int] = {}
    unchanged = 0

    for key in shared:
        old = before_map[key]
        new = after_map[key]
        transitions[f"{old}->{new}"] = transitions.get(f"{old}->{new}", 0) + 1
        if old == new:
            unchanged += 1
            continue
        if old != COVERED and new == COVERED:
            resolved.append(key)
        elif old == COVERED and new != COVERED:
            regressed.append(key)

    new_cells = sorted(after_keys - before_keys)
    dropped_cells = sorted(before_keys - after_keys)

    return AbsenceMapDelta(
        n_before=len(before),
        n_after=len(after),
        resolved=sorted(resolved),
        regressed=sorted(regressed),
        new_cells=new_cells,
        dropped_cells=dropped_cells,
        unchanged=unchanged,
        transitions=dict(sorted(transitions.items())),
    )
