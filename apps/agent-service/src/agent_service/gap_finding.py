"""§13.15 узел gap_analyzer / agent-layer gap aggregator (§11).

The §11 gap-scan tools emit raw, per-tool findings; the §13.15 ``gap_analyzer``
node's job is to fold that raw stream into a single, deduplicated,
severity-ranked ``state['gaps']`` list keyed by the §11.1 gap taxonomy.

Each raw finding is a ``dict`` with ``type``, ``entity_id``, ``description`` and
``severity``. :func:`aggregate_gaps` validates every ``type`` against
:data:`GAP_TYPES`, collapses duplicate ``(type, entity_id)`` pairs keeping the
worst severity, and returns frozen :class:`GapFinding` objects sorted
highest-severity-first (ties broken by ``type`` ascending).

:func:`is_critical` marks a finding whose ``type`` is in :data:`CRITICAL_TYPES`
(the §11.1 subset that must block an answer), and :func:`needs_review` filters an
aggregated list down to just those critical findings for the review queue.

Deterministic and dependency-free — the graph-backed scans that produce these
raw findings live in the §11 tool layer, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# §11.1 полная таксономия пробелов / full gap taxonomy (queryable gap kinds).
GAP_TYPES: frozenset[str] = frozenset(
    {
        "missing_property_value",
        "missing_unit",
        "missing_processing_parameter",
        "missing_baseline",
        "missing_equipment",
        "missing_source_span",
        "low_confidence_entity_resolution",
        "conflicting_measurements",
        "unverified_claim",
        "low_coverage_material",
        "orphan_entity",
    }
)

# §11.1 критические виды / critical subset that must block an answer (для review).
CRITICAL_TYPES: frozenset[str] = frozenset(
    {
        "missing_baseline",
        "missing_source_span",
        "conflicting_measurements",
        "unverified_claim",
    }
)


@dataclass(frozen=True)
class GapFinding:
    """§11.1 находка пробела / a single typed gap finding.

    ``type`` must be a member of :data:`GAP_TYPES`; ``severity`` must lie in the
    closed interval ``[0.0, 1.0]``. ``entity_id`` names the graph entity the gap
    hangs off and ``description`` is human-readable RU/EN context. Validation runs
    in :meth:`__post_init__`, so every constructed finding is well-formed.
    """

    type: str
    entity_id: str
    description: str
    severity: float

    def __post_init__(self) -> None:
        """Validate ``type`` against :data:`GAP_TYPES` and ``severity`` range."""
        if self.type not in GAP_TYPES:
            raise ValueError(f"unknown gap type: {self.type!r}")
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError(f"severity out of range [0.0, 1.0]: {self.severity!r}")

    def as_dict(self) -> dict[str, Any]:
        """Serialise for ``state['gaps']`` (JSON-friendly / для сериализации)."""
        return {
            "type": self.type,
            "entity_id": self.entity_id,
            "description": self.description,
            "severity": self.severity,
        }


def aggregate_gaps(raw: list[dict]) -> list[GapFinding]:
    """Fold raw gap-scan dicts into deduped, severity-ranked :class:`GapFinding`.

    Each raw dict is validated by constructing a :class:`GapFinding` (unknown
    ``type`` or out-of-range ``severity`` raises ``ValueError``). Duplicate
    ``(type, entity_id)`` pairs collapse to a single finding keeping the maximum
    severity (and that finding's description). The result is sorted by ``severity``
    descending, ties broken by ``type`` ascending.
    """
    best: dict[tuple[str, str], GapFinding] = {}
    for item in raw:
        finding = GapFinding(
            type=str(item["type"]),
            entity_id=str(item["entity_id"]),
            description=str(item.get("description", "")),
            severity=float(item["severity"]),
        )
        key = (finding.type, finding.entity_id)
        current = best.get(key)
        if current is None or finding.severity > current.severity:
            best[key] = finding

    return sorted(best.values(), key=lambda g: (-g.severity, g.type))


def is_critical(g: GapFinding) -> bool:
    """``True`` iff ``g.type`` is in :data:`CRITICAL_TYPES` (см. §11.1)."""
    return g.type in CRITICAL_TYPES


def needs_review(findings: list[GapFinding]) -> list[GapFinding]:
    """Filter ``findings`` down to the critical ones needing review (order kept)."""
    return [g for g in findings if is_critical(g)]
