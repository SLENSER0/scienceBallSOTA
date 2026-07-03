"""Expected extractor-missed-fact backlog (§25.11).

RU: Оценка ожидаемого числа фактов, которые экстрактор мог пропустить.
EN: Estimate of the expected number of facts the extractor likely missed.

For every empty coverage cell we already carry a ``confidence_of_absence``
(§25.3–25.5): the probability that the observed absence is *real* rather than an
extraction miss. The complementary probability

    missed_prob = 1 - confidence_of_absence

is therefore the per-cell expected number of *missed* facts (a Bernoulli mean).
Summing ``missed_prob`` over all cells yields the expected size of the
extractor-missed-fact backlog, and grouping the sum by material / property tells
us *where* the backlog concentrates. Cells that are already ``COVERED`` — or whose
absence confidence is not a usable number (``"unknown"``) — contribute ``0.0``:
a covered cell has no missing fact, and an unknown confidence gives us no signal.

``estimate_missed_facts`` also returns a ``ranked`` list of
``(material_id, property_name, missed_prob)`` in descending probability so a
reviewer can triage the most-likely-missed facts first.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "0.1.0"

# Absence statuses whose emptiness *may* hide a missed fact (§25.3).
# RU: статусы отсутствия; EN: absence statuses.
_ABSENCE_STATUSES: frozenset[str] = frozenset(
    {"POSSIBLE_ABSENCE", "LIKELY_ABSENCE", "CONFIRMED_ABSENCE", "ABSENCE"}
)


@dataclass(frozen=True, slots=True)
class MissedFactEstimate:
    """Expected extractor-missed-fact backlog (§25.11).

    RU: суммарная и разбитая по материалам/свойствам оценка пропущенных фактов.
    EN: total and per-material / per-property estimate of missed facts.
    """

    total_expected: float
    by_material: dict[str, float]
    by_property: dict[str, float]
    ranked: list[tuple[str, str, float]]

    def as_dict(self) -> dict[str, object]:
        """RU: сериализация в словарь. EN: serialise to a plain dict."""
        return {
            "schema_version": SCHEMA_VERSION,
            "total_expected": self.total_expected,
            "by_material": dict(self.by_material),
            "by_property": dict(self.by_property),
            "ranked": [list(row) for row in self.ranked],
        }


def missed_prob(cell: dict) -> float:
    """Per-cell expected missed-fact count = ``1 - confidence_of_absence``.

    RU: вероятность пропуска факта в ячейке. EN: probability a fact was missed.

    Returns ``0.0`` unless the cell is an absence status *and* carries a numeric
    ``confidence_of_absence`` (``COVERED`` or ``"unknown"`` → ``0.0``).
    """
    status = cell.get("status")
    if status not in _ABSENCE_STATUSES:
        return 0.0
    conf = cell.get("confidence_of_absence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return 0.0
    return 1.0 - float(conf)


def estimate_missed_facts(cells: list[dict]) -> MissedFactEstimate:
    """Aggregate per-cell missed probabilities into a backlog estimate (§25.11).

    RU: суммирует missed_prob по материалам и свойствам, ранжирует по убыванию.
    EN: sums missed_prob by material and property, ranks descending.
    """
    total = 0.0
    by_material: dict[str, float] = {}
    by_property: dict[str, float] = {}
    scored: list[tuple[str, str, float]] = []

    for cell in cells:
        prob = missed_prob(cell)
        if prob <= 0.0:
            continue
        material_id = str(cell.get("material_id", ""))
        property_name = str(cell.get("property_name", ""))
        total += prob
        by_material[material_id] = by_material.get(material_id, 0.0) + prob
        by_property[property_name] = by_property.get(property_name, 0.0) + prob
        scored.append((material_id, property_name, prob))

    ranked = sorted(scored, key=lambda row: row[2], reverse=True)
    return MissedFactEstimate(
        total_expected=total,
        by_material=by_material,
        by_property=by_property,
        ranked=ranked,
    )
