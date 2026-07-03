"""Techno-economic comparison builder (§24.11).

Технико-экономическое сравнение технологических решений — reads the CAPEX / OPEX /
NPV / payback / specific-energy indicators attached to ``TechnologySolution`` nodes
and lays them out as a comparison table you can rank one indicator at a time.

Two indicator sources are gathered (§24.11):

- ``TechnologySolution -[HAS_TECHNOECONOMIC_INDICATOR]-> TechnoEconomicIndicator``
  nodes (the dedicated relation), and
- any ``Measurement`` / indicator node linked to a solution whose ``property_name``
  is a techno-economic one — CAPEX (капитальные затраты), OPEX (операционные
  затраты), NPV (ЧДД), ``payback_period`` (срок окупаемости) or
  ``specific_energy_consumption`` (удельный расход энергии).

The module is read-only: it never writes to the graph. Results are frozen
dataclasses exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

# Node label for a technology solution being compared (§24.11).
SOLUTION_LABEL = "TechnologySolution"

# Node label for a dedicated techno-economic indicator measurement.
INDICATOR_LABEL = "TechnoEconomicIndicator"

# Relation linking a solution to its techno-economic indicator.
INDICATOR_REL = "HAS_TECHNOECONOMIC_INDICATOR"

# ``property_name`` values counted as techno-economic indicators (§24.11).
# capex=капзатраты, opex=операц. затраты, npv=ЧДД, payback_period=срок окупаемости,
# specific_energy_consumption=удельный расход энергии.
TECHNOECONOMIC_PROPERTIES: frozenset[str] = frozenset(
    {"capex", "opex", "npv", "payback_period", "specific_energy_consumption"}
)


@dataclass(frozen=True)
class TechnoEconomicIndicatorRow:
    """One techno-economic indicator measured for one solution (§24.11)."""

    solution_id: str
    indicator: str  # property_name: capex / opex / npv / payback_period / ...
    value: float | None
    unit: str | None
    evidence_ids: tuple[str, ...]  # linked Evidence ids (edges + SUPPORTED_BY), sorted
    indicator_id: str  # the indicator/measurement node id
    domain: str | None

    def as_dict(self) -> dict:
        """JSON row shape ``{solution_id, indicator, value, unit, evidence_ids}``."""
        return {
            "solution_id": self.solution_id,
            "indicator": self.indicator,
            "value": self.value,
            "unit": self.unit,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class TechnoEconomicComparison:
    """Techno-economic comparison over a graph (§24.11).

    ``solutions`` are the in-scope ``TechnologySolution`` ids; ``indicators`` is the
    flat list of measured indicator rows; ``by_indicator`` groups those rows by
    indicator name (capex/opex/...) for one-indicator-at-a-time ranking.
    """

    solutions: tuple[str, ...]
    indicators: tuple[TechnoEconomicIndicatorRow, ...]
    by_indicator: dict[str, tuple[TechnoEconomicIndicatorRow, ...]]

    @property
    def count(self) -> int:
        return len(self.indicators)

    def as_dict(self) -> dict:
        return {
            "solutions": list(self.solutions),
            "indicators": [r.as_dict() for r in self.indicators],
            "by_indicator": {k: [r.as_dict() for r in v] for k, v in self.by_indicator.items()},
        }


def _parse_evidence(raw: object) -> list[str]:
    """Parse an edge ``evidence_ids`` JSON string into a list (empty on failure)."""
    if not isinstance(raw, str) or not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _solution_ids(store: KuzuGraphStore, domain: str | None) -> list[str]:
    """All in-scope ``TechnologySolution`` ids, optionally scoped by ``domain``."""
    cypher = "MATCH (s:Node) WHERE s.label=$label "
    params: dict[str, object] = {"label": SOLUTION_LABEL}
    if domain is not None:
        cypher += "AND s.domain=$domain "
        params["domain"] = domain
    cypher += "RETURN s.id ORDER BY s.id"
    return [r[0] for r in store.rows(cypher, params)]


def _indicator_hits(
    store: KuzuGraphStore, domain: str | None
) -> dict[tuple[str, str], dict[str, object]]:
    """Gather ``(solution_id, indicator_id) -> raw fields`` from both sources (§24.11).

    Source A walks the dedicated ``HAS_TECHNOECONOMIC_INDICATOR`` relation; source B
    catches any solution-linked node whose ``property_name`` is techno-economic. The
    two are merged (deduped) on the ``(solution, indicator)`` pair.
    """
    dom_clause = "AND s.domain=$domain " if domain is not None else ""
    params: dict[str, object] = {}
    if domain is not None:
        params["domain"] = domain

    hits: dict[tuple[str, str], dict[str, object]] = {}

    # Source A: solution -[HAS_TECHNOECONOMIC_INDICATOR]-> indicator node.
    rows_a = store.rows(
        "MATCH (s:Node)-[r:Rel]->(ind:Node) "
        f"WHERE s.label=$label AND r.type=$rel {dom_clause}"
        "RETURN s.id, ind.id, ind.property_name, ind.value_normalized, "
        "ind.normalized_unit, ind.domain, r.evidence_ids ORDER BY s.id, ind.id",
        {"label": SOLUTION_LABEL, "rel": INDICATOR_REL, **params},
    )
    for sid, iid, prop, val, unit, idom, edge_eids in rows_a:
        hits[(sid, iid)] = {
            "property_name": prop,
            "value": val,
            "unit": unit,
            "domain": idom,
            "edge_evidence": _parse_evidence(edge_eids),
        }

    # Source B: any solution-linked node with a techno-economic property_name.
    rows_b = store.rows(
        "MATCH (s:Node)-[r:Rel]-(m:Node) "
        f"WHERE s.label=$label AND m.property_name IN $props {dom_clause}"
        "RETURN DISTINCT s.id, m.id, m.property_name, m.value_normalized, "
        "m.normalized_unit, m.domain, r.evidence_ids ORDER BY s.id, m.id",
        {"label": SOLUTION_LABEL, "props": sorted(TECHNOECONOMIC_PROPERTIES), **params},
    )
    for sid, iid, prop, val, unit, idom, edge_eids in rows_b:
        entry = hits.setdefault(
            (sid, iid),
            {"property_name": prop, "value": val, "unit": unit, "domain": idom},
        )
        edge_ev = set(entry.get("edge_evidence", []))  # type: ignore[arg-type]
        edge_ev.update(_parse_evidence(edge_eids))
        entry["edge_evidence"] = sorted(edge_ev)

    return hits


def _indicator_evidence(
    store: KuzuGraphStore, indicator_id: str, edge_evidence: list[str]
) -> tuple[str, ...]:
    """Evidence ids for an indicator: linking-edge ids + ``SUPPORTED_BY`` Evidence."""
    evidence: set[str] = set(edge_evidence)
    rows = store.rows(
        "MATCH (m:Node {id:$mid})-[r:Rel]->(e:Node) "
        "WHERE r.type='SUPPORTED_BY' AND e.label='Evidence' "
        "RETURN DISTINCT e.id, r.evidence_ids ORDER BY e.id",
        {"mid": indicator_id},
    )
    for eid, edge_eids in rows:
        evidence.add(eid)
        evidence.update(_parse_evidence(edge_eids))
    return tuple(sorted(evidence))


def _resolve_indicator_name(store: KuzuGraphStore, indicator_id: str, prop: object) -> str:
    """Indicator key: the ``property_name`` if present, else the node name / id."""
    if isinstance(prop, str) and prop:
        return prop
    node = store.get_node(indicator_id)
    if node:
        name = node.get("name") or node.get("canonical_name")
        if isinstance(name, str) and name:
            return name
    return indicator_id


def compare_technoeconomics(
    store: KuzuGraphStore, *, domain: str | None = None
) -> TechnoEconomicComparison:
    """Build a techno-economic comparison over ``store`` (§24.11).

    Collects every in-scope ``TechnologySolution`` and the CAPEX/OPEX/NPV/payback/
    specific-energy indicators attached to it, resolving linked Evidence, and groups
    the rows by indicator name. An empty or ``domain``-absent graph yields an empty
    comparison (graceful, no error).
    """
    solutions = tuple(_solution_ids(store, domain))
    hits = _indicator_hits(store, domain)

    rows: list[TechnoEconomicIndicatorRow] = []
    for (sid, iid), fields in hits.items():
        prop = fields.get("property_name")
        indicator = _resolve_indicator_name(store, iid, prop)
        raw_val = fields.get("value")
        value = float(raw_val) if isinstance(raw_val, (int, float)) else None
        unit = fields.get("unit")
        evidence = _indicator_evidence(
            store,
            iid,
            list(fields.get("edge_evidence", [])),  # type: ignore[arg-type]
        )
        rows.append(
            TechnoEconomicIndicatorRow(
                solution_id=sid,
                indicator=indicator,
                value=value,
                unit=unit if isinstance(unit, str) else None,
                evidence_ids=evidence,
                indicator_id=iid,
                domain=fields.get("domain") if isinstance(fields.get("domain"), str) else None,
            )
        )

    rows.sort(key=lambda r: (r.indicator, r.solution_id, r.indicator_id))

    by_indicator: dict[str, list[TechnoEconomicIndicatorRow]] = {}
    for row in rows:
        by_indicator.setdefault(row.indicator, []).append(row)
    frozen_index = {k: tuple(v) for k, v in sorted(by_indicator.items())}

    return TechnoEconomicComparison(
        solutions=solutions,
        indicators=tuple(rows),
        by_indicator=frozen_index,
    )


def rank_by_indicator(
    comparison: TechnoEconomicComparison, indicator: str, *, ascending: bool = True
) -> list[TechnoEconomicIndicatorRow]:
    """Rank one indicator's rows by value (§24.11).

    Returns the rows for ``indicator`` ordered by numeric value — ascending by
    default (e.g. cheapest CAPEX first). Rows with no value are placed last in both
    directions. An unknown indicator yields an empty list (graceful).
    """
    rows = comparison.by_indicator.get(indicator, ())
    present = [r for r in rows if r.value is not None]
    absent = [r for r in rows if r.value is None]
    present.sort(key=lambda r: r.value, reverse=not ascending)  # type: ignore[arg-type,return-value]
    return present + absent
