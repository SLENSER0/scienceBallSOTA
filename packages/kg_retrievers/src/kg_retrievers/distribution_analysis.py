"""Metal distribution / partition-coefficient analysis (§24.7).

Распределение металлов по фазам — reads ``distribution_coefficient`` Measurements
out of the graph and reports, per measurement, the *phase* Materials it is
partitioned between (matte / slag / gas / metal — штейн / шлак / газ / металл).

A distribution coefficient ``L`` = concentration in the enriched phase divided by
the concentration in the depleted phase; e.g. copper reports strongly to the matte
in flash smelting (взвешенная плавка) with ``L(Cu) ≈ 25``. This module is
read-only: it walks ``DISTRIBUTES_BETWEEN`` / ``PARTITIONED_TO_PHASE`` edges and
never writes to the graph.

Results are frozen dataclasses exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

# Measurement property that marks a metal distribution / partition coefficient.
DISTRIBUTION_PROPERTY = "distribution_coefficient"

# Material classes that count as a *phase* of a smelting/separation system (§24.7).
# matte=штейн, slag=шлак, gas=газ, metal=металл.
PHASE_CLASSES: frozenset[str] = frozenset({"matte", "slag", "gas", "metal"})

# Relationship types that link a coefficient Measurement to its phase Materials.
PARTITION_REL_TYPES: tuple[str, ...] = ("DISTRIBUTES_BETWEEN", "PARTITIONED_TO_PHASE")

_REL_TYPE_LIST = ", ".join(f"'{t}'" for t in PARTITION_REL_TYPES)


def partition_ratio(value: float | None) -> float | None:
    """Fraction of metal reporting to the enriched phase for a coefficient ``L``.

    Доля металла в обогащённой фазе = ``L / (1 + L)`` (§24.7). For ``L(Cu)=25``
    this is ≈ 0.962, i.e. ~96 % of the copper reports to the matte. Returns
    ``None`` for a missing or negative coefficient.
    """
    if value is None or value < 0:
        return None
    return value / (1.0 + value)


@dataclass(frozen=True)
class DistributionCoefficient:
    """One ``distribution_coefficient`` Measurement and its phase context (§24.7)."""

    measurement_id: str
    value: float | None
    phases: tuple[str, ...]  # distinct phase classes (matte/slag/gas/metal), sorted
    phase_ids: tuple[str, ...]  # phase Material node ids, sorted
    evidence_ids: tuple[str, ...]  # linked Evidence ids (edges + SUPPORTED_BY), sorted
    domain: str | None

    @property
    def ratio(self) -> float | None:
        """Enriched-phase fraction ``L/(1+L)`` (доля в обогащённой фазе)."""
        return partition_ratio(self.value)

    @property
    def phase_pair(self) -> str:
        """Stable ``"matte|slag"``-style key over this coefficient's phases."""
        return "|".join(self.phases)

    def as_dict(self) -> dict:
        return {
            "measurement_id": self.measurement_id,
            "value": self.value,
            "phases": list(self.phases),
            "phase_ids": list(self.phase_ids),
            "evidence_ids": list(self.evidence_ids),
            "domain": self.domain,
            "ratio": self.ratio,
        }


@dataclass(frozen=True)
class DistributionReport:
    """Metal partition report over a graph (§24.7): coefficients + phase-pair index."""

    coefficients: tuple[DistributionCoefficient, ...]
    by_phase_pair: dict[str, tuple[str, ...]]  # "matte|slag" -> measurement ids

    @property
    def count(self) -> int:
        return len(self.coefficients)

    def as_dict(self) -> dict:
        return {
            "count": self.count,
            "coefficients": [c.as_dict() for c in self.coefficients],
            "by_phase_pair": {k: list(v) for k, v in self.by_phase_pair.items()},
        }


def _coefficient_measurements(
    store: KuzuGraphStore, domain: str | None
) -> list[tuple[str, float | None, str | None]]:
    """All ``distribution_coefficient`` Measurements, optionally domain-filtered."""
    cypher = "MATCH (m:Node) WHERE m.label='Measurement' AND m.property_name=$prop "
    params: dict[str, object] = {"prop": DISTRIBUTION_PROPERTY}
    if domain is not None:
        cypher += "AND m.domain=$domain "
        params["domain"] = domain
    cypher += "RETURN m.id, m.value_normalized, m.domain ORDER BY m.id"
    rows = store.rows(cypher, params)
    return [(r[0], r[1], r[2]) for r in rows]


def _phase_links(
    store: KuzuGraphStore, measurement_id: str
) -> tuple[list[str], list[str], list[str]]:
    """Return (phase classes, phase material ids, edge evidence ids) for a coefficient.

    Walks ``DISTRIBUTES_BETWEEN`` / ``PARTITIONED_TO_PHASE`` edges (either
    direction) to Materials, keeping only recognised phase classes (§24.7).
    """
    rows = store.rows(
        "MATCH (m:Node {id:$mid})-[r:Rel]-(mat:Node) "
        f"WHERE r.type IN [{_REL_TYPE_LIST}] AND mat.label='Material' "
        "RETURN DISTINCT mat.id, mat.material_class, r.evidence_ids ORDER BY mat.id",
        {"mid": measurement_id},
    )
    classes: set[str] = set()
    ids: set[str] = set()
    evidence: set[str] = set()
    for mat_id, mat_class, edge_eids in rows:
        if mat_class not in PHASE_CLASSES:
            continue
        classes.add(mat_class)
        ids.add(mat_id)
        for eid in _parse_evidence(edge_eids):
            evidence.add(eid)
    return sorted(classes), sorted(ids), sorted(evidence)


def _supported_evidence(store: KuzuGraphStore, measurement_id: str) -> list[str]:
    """Evidence node ids the measurement is ``SUPPORTED_BY`` (Evidence only)."""
    rows = store.rows(
        "MATCH (m:Node {id:$mid})-[r:Rel]->(e:Node) "
        "WHERE r.type='SUPPORTED_BY' AND e.label='Evidence' "
        "RETURN DISTINCT e.id ORDER BY e.id",
        {"mid": measurement_id},
    )
    return [r[0] for r in rows]


def _parse_evidence(raw: object) -> list[str]:
    """Parse an edge ``evidence_ids`` JSON string into a list (empty on failure)."""
    if not isinstance(raw, str) or not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def analyze_distribution(store: KuzuGraphStore, *, domain: str | None = None) -> DistributionReport:
    """Build a metal distribution-coefficient report over ``store`` (§24.7).

    Finds every ``distribution_coefficient`` Measurement (optionally scoped to
    ``domain``), resolves the phase Materials it is partitioned between, and
    indexes them by phase pair. An empty or ``domain``-absent graph yields an
    empty report (graceful, no error).
    """
    coefficients: list[DistributionCoefficient] = []
    by_phase_pair: dict[str, list[str]] = {}

    for measurement_id, value, mdomain in _coefficient_measurements(store, domain):
        classes, phase_ids, edge_evidence = _phase_links(store, measurement_id)
        evidence = sorted(set(edge_evidence) | set(_supported_evidence(store, measurement_id)))
        coeff = DistributionCoefficient(
            measurement_id=measurement_id,
            value=float(value) if value is not None else None,
            phases=tuple(classes),
            phase_ids=tuple(phase_ids),
            evidence_ids=tuple(evidence),
            domain=mdomain,
        )
        coefficients.append(coeff)
        if coeff.phases:
            by_phase_pair.setdefault(coeff.phase_pair, []).append(measurement_id)

    frozen_index = {k: tuple(sorted(v)) for k, v in sorted(by_phase_pair.items())}
    return DistributionReport(coefficients=tuple(coefficients), by_phase_pair=frozen_index)
