"""§13.16 unit-consistency verifier / проверка согласованности единиц (§7.5 Node 9).

Complements :mod:`agent_service.answer_validator` (numeric-claim grounding) with
the §7.5 Node 9 «units not mixed» rule: one physical quantity (одна физическая
величина) must be reported in a single canonical unit. When a synthesised answer
mixes, say, hardness in ``HV`` and ``MPa`` — two different scales for the same
quantity — the numbers are no longer comparable and the mix is flagged.

Deterministic and dependency-free. :data:`QUANTITY_UNITS` maps each recognised
canonical unit-string to a quantity key; :func:`find_unit_conflicts` groups claims
by that key and reports any quantity carrying two or more distinct units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Canonical unit-string -> quantity key (единица измерения -> физическая величина).
# The registry of units this check recognises: each canonical unit-string names the
# physical quantity it belongs to. Mixing two distinct units for one quantity within
# a single answer is exactly what §7.5 Node 9 forbids.
QUANTITY_UNITS: dict[str, str] = {
    "HV": "hardness",
    "MPa": "strength",
    "GPa": "strength",
    "°C": "temperature",
    "C": "temperature",
    "h": "time",
}


@dataclass(frozen=True)
class UnitConflict:
    """A single quantity reported in two or more distinct canonical units.

    ``quantity`` is the quantity key (e.g. ``"hardness"``) and ``units`` holds the
    conflicting unit-strings, sorted and de-duplicated (отсортированы, без повторов).
    """

    quantity: str
    units: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{quantity, units}`` with ``units`` as a plain list."""
        return {"quantity": self.quantity, "units": list(self.units)}


def find_unit_conflicts(claims: list[dict]) -> list[UnitConflict]:
    """Flag every quantity used with >=2 distinct canonical units (§7.5 Node 9).

    Each claim is a dict with a ``"quantity"`` key (the physical quantity, e.g.
    ``"hardness"``) and a ``"unit"`` key (its canonical unit-string). Claims are
    grouped by their ``"quantity"`` and the distinct units seen for each quantity are
    collected; a :class:`UnitConflict` is emitted for every quantity holding two or
    more distinct units. Conflicts are returned in first-seen order of the quantity;
    ``units`` inside each conflict are sorted and de-duplicated (без повторов).
    """
    order: list[str] = []
    seen: dict[str, set[str]] = {}
    for claim in claims:
        unit = claim.get("unit")
        quantity = claim.get("quantity")
        if unit is None or quantity is None:
            continue
        if quantity not in seen:
            seen[quantity] = set()
            order.append(quantity)
        seen[quantity].add(unit)
    conflicts: list[UnitConflict] = []
    for quantity in order:
        units = seen[quantity]
        if len(units) >= 2:
            conflicts.append(UnitConflict(quantity=quantity, units=tuple(sorted(units))))
    return conflicts


def is_consistent(claims: list[dict]) -> bool:
    """Return ``True`` when no quantity mixes canonical units (нет конфликтов)."""
    return not find_unit_conflicts(claims)
