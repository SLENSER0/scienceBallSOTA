"""Chat answer warning-panel aggregation (§15.9 / §5.2.2).

The chat surface must show the reader a single *warning panel* (панель
предупреждений) that rolls up three orthogonal quality signals accompanying an
answer:

* **contradictions** — divergent measurements flagged by the contradiction
  detector (противоречия);
* **low-confidence results** — retrieved nodes whose ``confidence`` falls below
  a threshold (низкая уверенность);
* **missing-data gaps** — gaps whose :class:`~kg_schema.enums.GapType` is one of
  the ``missing_*`` families (пропуски данных).

No existing module aggregates all three, so this module provides
:data:`MISSING_DATA_TYPES` (the ``missing_*`` gap-type strings) and
:func:`build_warning_panel`, which folds the three inputs into an immutable
:class:`WarningPanel`. It is a pure function over plain dicts — no store, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_schema.enums import GapType

_log = get_logger("answer_warning_panel")

# The ``missing_*`` gap-type strings (§15.1) — the "missing-data" family. / Семейство пропусков.
MISSING_DATA_TYPES: frozenset[str] = frozenset(
    str(gt) for gt in GapType if str(gt).startswith("missing_")
)


def _is_critical(item: dict) -> bool:
    """True if a single input item carries ``severity == 'critical'``. / Критично?"""
    return item.get("severity") == "critical"


@dataclass(frozen=True)
class WarningPanel:
    """Aggregated warning panel for one answer (§15.9 / §5.2.2).

    ``severity`` is ``'critical'`` when any contributing item is critical, else
    ``'high'`` when at least one warning exists, else ``'none'``. ``items`` is the
    ordered union of the contributing items: contradictions, then missing-data
    gaps, then low-confidence nodes.
    """

    contradiction_count: int
    low_confidence_count: int
    missing_data_count: int
    severity: str
    has_warnings: bool
    items: tuple[dict, ...]

    def as_dict(self) -> dict:
        return {
            "contradiction_count": self.contradiction_count,
            "low_confidence_count": self.low_confidence_count,
            "missing_data_count": self.missing_data_count,
            "severity": self.severity,
            "has_warnings": self.has_warnings,
            "items": [dict(it) for it in self.items],
        }


def build_warning_panel(
    contradictions: list[dict],
    low_confidence_nodes: list[dict],
    gaps: list[dict],
    *,
    confidence_threshold: float = 0.5,
) -> WarningPanel:
    """Fold three quality signals into a :class:`WarningPanel` (§15.9 / §5.2.2).

    Аргументы / Arguments:
        contradictions: contradiction records (all counted).
        low_confidence_nodes: retrieved nodes; kept iff ``confidence`` is present
            and strictly below ``confidence_threshold``.
        gaps: gap records; counted iff ``gap_type`` is in :data:`MISSING_DATA_TYPES`.
        confidence_threshold: exclusive upper bound for "low confidence".

    Items are ordered contradictions → missing-data gaps → low-confidence nodes.
    """
    contradiction_items = list(contradictions)

    missing_items = [g for g in gaps if g.get("gap_type") in MISSING_DATA_TYPES]

    low_conf_items = [
        n
        for n in low_confidence_nodes
        if n.get("confidence") is not None and n["confidence"] < confidence_threshold
    ]

    items: tuple[dict, ...] = tuple(contradiction_items + missing_items + low_conf_items)

    contradiction_count = len(contradiction_items)
    missing_data_count = len(missing_items)
    low_confidence_count = len(low_conf_items)
    total = contradiction_count + missing_data_count + low_confidence_count

    if any(_is_critical(it) for it in items):
        severity = "critical"
    elif total > 0:
        severity = "high"
    else:
        severity = "none"

    return WarningPanel(
        contradiction_count=contradiction_count,
        low_confidence_count=low_confidence_count,
        missing_data_count=missing_data_count,
        severity=severity,
        has_warnings=total > 0,
        items=items,
    )
