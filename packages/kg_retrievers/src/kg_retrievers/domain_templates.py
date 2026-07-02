"""Six domain query templates (§24.9 / §12) as pure functions.

Each template answers one of the acceptance scenarios directly against the generic
Kuzu ``(:Node)`` / ``-[:Rel {type}]-`` model, using ONLY declared ``RelType`` edge
types (kg_schema.relationships). A template gathers the relevant
solutions/methods, their measurements, the materials and indicators they touch,
plus any gaps / contradictions, collects evidence (both node-level ``Evidence`` /
``Paper`` neighbours and edge-level ``evidence_ids`` provenance), and returns a
plain ``dict`` of id lists together with a ``GraphResponse`` subgraph for the UI.

The functions are stateless and read-only — they never mutate the graph — so the
agent / API layer can call them as deterministic, evidence-first retrieval tools.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from kg_common import GraphResponse, get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema import RelType

_log = get_logger("domain_templates")

# Node labels that count as an answer "solution/method" across templates.
SOLUTION_LABELS: list[str] = ["TechnologySolution", "Method"]
# Labels treated as evidence when reachable from a core node.
EVIDENCE_LABELS: list[str] = ["Evidence", "Paper"]

# How far to expand the returned subgraph around the collected core ids.
SUBGRAPH_EXPAND = 1


def _rels(*rel_types: RelType) -> list[str]:
    """Cast declared ``RelType`` members to plain strings for Cypher params."""
    return [str(r) for r in rel_types]


def _uniq(ids: list[str]) -> list[str]:
    """Deterministic de-dupe (sorted) that drops falsy ids."""
    return sorted({i for i in ids if i})


def _evidence_for(store: KuzuGraphStore, core_ids: list[str]) -> list[str]:
    """Evidence ids for a set of core nodes (node neighbours + edge provenance).

    Collects both directly-linked ``Evidence`` / ``Paper`` nodes and the
    ``evidence_ids`` JSON arrays carried on the edges incident to the core nodes,
    so an answer is always traceable to its source spans (§7.3).
    """
    if not core_ids:
        return []
    found: set[str] = set()
    for row in store.rows(
        "MATCH (a:Node)-[e:Rel]-(b:Node) "
        "WHERE a.id IN $ids AND b.label IN $labels RETURN DISTINCT b.id",
        {"ids": core_ids, "labels": EVIDENCE_LABELS},
    ):
        if row[0]:
            found.add(row[0])
    for row in store.rows(
        "MATCH (a:Node)-[e:Rel]-(:Node) "
        "WHERE a.id IN $ids AND e.evidence_ids IS NOT NULL RETURN e.evidence_ids",
        {"ids": core_ids},
    ):
        raw = row[0]
        if not isinstance(raw, str):
            continue
        try:
            found.update(str(x) for x in json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    return sorted(found)


def _contradictions_for(store: KuzuGraphStore, core_ids: list[str]) -> list[str]:
    """Contradiction node ids touching any of the core nodes (§15)."""
    if not core_ids:
        return []
    rows = store.rows(
        "MATCH (c:Node)-[e:Rel]-(x:Node) "
        "WHERE c.label='Contradiction' AND x.id IN $ids RETURN DISTINCT c.id",
        {"ids": core_ids},
    )
    return _uniq([r[0] for r in rows])


def _group_by_practice(store: KuzuGraphStore, ids: list[str]) -> dict[str, list[str]]:
    """Group solution ids by their ``practice_type`` (russia / foreign / …) — §12."""
    grouped: dict[str, list[str]] = {}
    for nid in ids:
        nd = store.get_node(nid)
        pt = (nd or {}).get("practice_type") or "unknown"
        grouped.setdefault(pt, []).append(nid)
    for pt in grouped:
        grouped[pt] = _uniq(grouped[pt])
    return grouped


def _build_result(
    store: KuzuGraphStore,
    *,
    scenario: str,
    solutions: list[str],
    measurements: list[str] | None = None,
    materials: list[str] | None = None,
    indicators: list[str] | None = None,
    gaps: list[str] | None = None,
    facilities: list[str] | None = None,
    extra_graph_ids: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Assemble the uniform template result + a subgraph over every collected id."""
    solutions = _uniq(solutions)
    measurements = _uniq(measurements or [])
    materials = _uniq(materials or [])
    indicators = _uniq(indicators or [])
    gaps = _uniq(gaps or [])
    facilities = _uniq(facilities or [])

    core = _uniq([*solutions, *measurements, *materials, *indicators, *gaps, *facilities])
    evidence = _evidence_for(store, core)
    contradictions = _contradictions_for(store, core)

    all_ids = _uniq([*core, *evidence, *contradictions, *(extra_graph_ids or [])])
    graph = store.subgraph_from_ids(all_ids, expand=SUBGRAPH_EXPAND) if all_ids else GraphResponse()
    result: dict[str, Any] = {
        "scenario": scenario,
        "solutions": solutions,
        "measurements": measurements,
        "evidence": evidence,
        "materials": materials,
        "indicators": indicators,
        "gaps": gaps,
        "facilities": facilities,
        "contradictions": contradictions,
        "graph": graph,
    }
    result.update(extra)
    _log.info(
        "domain_template.done",
        scenario=scenario,
        solutions=len(solutions),
        measurements=len(measurements),
        evidence=len(evidence),
        gaps=len(gaps),
        contradictions=len(contradictions),
    )
    return result


# =====================================================================
# 1) Water desalination suitability (SO4/Cl/Ca/Mg/Na, TDS target)
# =====================================================================
def water_desalination_suitability(
    store: KuzuGraphStore, ions: list[str], target_tds: float
) -> dict[str, Any]:
    """Desalination methods that treat a mine/process water for a given TDS target.

    Finds ``TechnologySolution`` nodes linked to a water ``Material`` via
    ``TREATS_WATER`` / ``REMOVES_CONTAMINANT``, the water's ion-concentration and
    TDS-target ``Measurement`` nodes (via ``ABOUT_MATERIAL``), and their evidence.
    ``ions`` filters which ion measurements are returned; ``target_tds`` is echoed
    as the requested constraint and used to flag whether the seeded TDS target is
    achievable.
    """
    rows = store.rows(
        "MATCH (sol:Node)-[r:Rel]-(w:Node) "
        "WHERE r.type IN $rels AND sol.label IN $sol_labels AND w.label='Material' "
        "AND (w.domain='water_treatment' OR w.material_class='water') "
        "RETURN DISTINCT sol.id, w.id",
        {
            "rels": _rels(RelType.TREATS_WATER, RelType.REMOVES_CONTAMINANT),
            "sol_labels": SOLUTION_LABELS,
        },
    )
    solutions = _uniq([r[0] for r in rows])
    water_ids = _uniq([r[1] for r in rows])

    ion_terms = [t.lower() for t in (ions or []) if t]
    measurements: list[str] = []
    tds_met = False
    if water_ids:
        for mid, prop, name, val in store.rows(
            "MATCH (m:Node)-[r:Rel]-(w:Node) "
            "WHERE r.type=$rel AND m.label='Measurement' AND w.id IN $water "
            "RETURN m.id, m.property_name, m.name, m.value_normalized",
            {"rel": str(RelType.ABOUT_MATERIAL), "water": water_ids},
        ):
            prop_l = (prop or "").lower()
            name_l = (name or "").lower()
            if prop_l == "total_dissolved_solids":
                measurements.append(mid)
                if val is not None and float(val) <= float(target_tds):
                    tds_met = True
                continue
            if not ion_terms or any(t in name_l or t in prop_l for t in ion_terms):
                measurements.append(mid)

    return _build_result(
        store,
        scenario="water_desalination_suitability",
        solutions=solutions,
        measurements=measurements,
        materials=water_ids,
        target_tds=float(target_tds),
        requested_ions=list(ions or []),
        target_tds_met=tds_met,
        suitable=bool(solutions),
    )


# =====================================================================
# 2) Nickel electrowinning — catholyte circulation solutions
# =====================================================================
def nickel_catholyte_circulation_solutions(store: KuzuGraphStore) -> dict[str, Any]:
    """Catholyte-circulation schemes for Ni electrowinning + their regime measurements.

    Finds solutions linked via ``CIRCULATES_ELECTROLYTE``, the ``Measurement`` nodes
    describing their regime (via ``ABOUT_REGIME`` — notably ``flow_velocity``), the
    electrolyte / metal ``Material`` they apply to, and any contradictions between
    divergent regime values (the seeded 0.2 vs 0.5 m/s conflict).
    """
    solutions = _uniq(
        [
            r[0]
            for r in store.rows(
                "MATCH (sol:Node)-[r:Rel]-(el:Node) "
                "WHERE r.type=$rel AND sol.label IN $sol_labels AND el.label='Material' "
                "RETURN DISTINCT sol.id",
                {"rel": str(RelType.CIRCULATES_ELECTROLYTE), "sol_labels": SOLUTION_LABELS},
            )
        ]
    )
    measurements: list[str] = []
    if solutions:
        measurements = _uniq(
            [
                r[0]
                for r in store.rows(
                    "MATCH (m:Node)-[r:Rel]-(sol:Node) "
                    "WHERE r.type=$rel AND m.label='Measurement' AND sol.id IN $sols "
                    "RETURN DISTINCT m.id",
                    {"rel": str(RelType.ABOUT_REGIME), "sols": solutions},
                )
            ]
        )
    materials: list[str] = []
    if solutions:
        materials = _uniq(
            [
                r[0]
                for r in store.rows(
                    "MATCH (sol:Node)-[r:Rel]-(mat:Node) "
                    "WHERE r.type IN $rels AND mat.label='Material' AND sol.id IN $sols "
                    "RETURN DISTINCT mat.id",
                    {
                        "rels": _rels(RelType.APPLIES_TO, RelType.CIRCULATES_ELECTROLYTE),
                        "sols": solutions,
                    },
                )
            ]
        )
    return _build_result(
        store,
        scenario="nickel_catholyte_circulation_solutions",
        solutions=solutions,
        measurements=measurements,
        materials=materials,
    )


# =====================================================================
# 3) Precious metals (Au/Ag/PGM) partitioning matte vs slag
# =====================================================================
def precious_metals_partitioning(store: KuzuGraphStore, years: int | None = None) -> dict[str, Any]:
    """Distribution coefficients of Au/Ag/PGM between phases (matte vs slag).

    Finds ``Measurement`` nodes linked via ``DISTRIBUTES_BETWEEN`` to the phase
    ``Material`` nodes and their evidence. When ``years`` is given, only keeps
    measurements whose supporting ``Paper`` is within the last ``years`` (by year).
    """
    meas_rows = store.rows(
        "MATCH (m:Node)-[r:Rel]-(phase:Node) "
        "WHERE r.type=$rel AND m.label='Measurement' AND phase.label='Material' "
        "RETURN DISTINCT m.id, phase.id",
        {"rel": str(RelType.DISTRIBUTES_BETWEEN)},
    )
    measurements = _uniq([r[0] for r in meas_rows])
    materials = _uniq([r[1] for r in meas_rows])

    if years is not None and measurements:
        cutoff = datetime.now(UTC).year - int(years)
        year_by_meas: dict[str, int] = {}
        for mid, pyear in store.rows(
            "MATCH (m:Node)-[r:Rel]-(p:Node) "
            "WHERE r.type=$rel AND p.label='Paper' AND m.id IN $meas "
            "AND p.year IS NOT NULL RETURN m.id, max(p.year)",
            {"rel": str(RelType.SUPPORTED_BY), "meas": measurements},
        ):
            if pyear is not None:
                year_by_meas[mid] = int(pyear)
        # Keep a measurement if it has no dated paper (don't silently drop
        # unsupported facts) or its most recent supporting paper is recent enough.
        measurements = _uniq([m for m in measurements if year_by_meas.get(m, cutoff) >= cutoff])
        # Re-derive phases from the surviving measurements only.
        if measurements:
            materials = _uniq(
                [
                    r[0]
                    for r in store.rows(
                        "MATCH (m:Node)-[r:Rel]-(phase:Node) "
                        "WHERE r.type=$rel AND phase.label='Material' AND m.id IN $meas "
                        "RETURN DISTINCT phase.id",
                        {"rel": str(RelType.DISTRIBUTES_BETWEEN), "meas": measurements},
                    )
                ]
            )
        else:
            materials = []

    return _build_result(
        store,
        scenario="precious_metals_partitioning",
        solutions=[],
        measurements=measurements,
        materials=materials,
        phases=materials,
        last_n_years=years,
    )


# =====================================================================
# 4) Mine water deep injection — Russia vs foreign practice
# =====================================================================
def mine_water_deep_injection(store: KuzuGraphStore) -> dict[str, Any]:
    """Deep-well injection solutions for mine water, grouped by practice (RU vs foreign).

    Finds solutions via ``INJECTS_INTO_HORIZON`` to a ``Facility``, the foreign
    counterparts they are compared with (``COMPARES_WITH``), their techno-economic
    indicators (``HAS_TECHNOECONOMIC_INDICATOR``) and evidence.
    """
    inj_rows = store.rows(
        "MATCH (sol:Node)-[r:Rel]-(f:Node) "
        "WHERE r.type=$rel AND sol.label IN $sol_labels AND f.label='Facility' "
        "RETURN DISTINCT sol.id, f.id",
        {"rel": str(RelType.INJECTS_INTO_HORIZON), "sol_labels": SOLUTION_LABELS},
    )
    solutions = _uniq([r[0] for r in inj_rows])
    facilities = _uniq([r[1] for r in inj_rows])

    if solutions:
        compared = _uniq(
            [
                r[0]
                for r in store.rows(
                    "MATCH (a:Node)-[r:Rel]-(b:Node) "
                    "WHERE r.type=$rel AND a.id IN $sols AND b.label IN $sol_labels "
                    "RETURN DISTINCT b.id",
                    {
                        "rel": str(RelType.COMPARES_WITH),
                        "sols": solutions,
                        "sol_labels": SOLUTION_LABELS,
                    },
                )
            ]
        )
        solutions = _uniq([*solutions, *compared])

    indicators: list[str] = []
    if solutions:
        indicators = _uniq(
            [
                r[0]
                for r in store.rows(
                    "MATCH (sol:Node)-[r:Rel]-(tei:Node) "
                    "WHERE r.type=$rel AND sol.id IN $sols "
                    "AND tei.label='TechnoEconomicIndicator' RETURN DISTINCT tei.id",
                    {"rel": str(RelType.HAS_TECHNOECONOMIC_INDICATOR), "sols": solutions},
                )
            ]
        )

    return _build_result(
        store,
        scenario="mine_water_deep_injection",
        solutions=solutions,
        indicators=indicators,
        facilities=facilities,
        grouped_by_practice=_group_by_practice(store, solutions),
    )


# =====================================================================
# 5) SO2 removal / flue-gas cleaning methods
# =====================================================================
def so2_removal_methods(store: KuzuGraphStore) -> dict[str, Any]:
    """Methods that remove SO2 from flue gas + their removal-efficiency measurements.

    Finds solutions linked via ``REMOVES_CONTAMINANT`` to a *gas* ``Material``
    (scoped by ``material_class='gas'`` / SO2 aliases so water methods don't leak
    in), and the ``Measurement`` nodes describing their regime (``ABOUT_REGIME``).
    """
    gas_rows = store.rows(
        "MATCH (sol:Node)-[r:Rel]-(gas:Node) "
        "WHERE r.type=$rel AND sol.label IN $sol_labels AND gas.label='Material' "
        "AND (gas.material_class='gas' OR lower(gas.aliases_text) CONTAINS 'so2') "
        "RETURN DISTINCT sol.id, gas.id",
        {"rel": str(RelType.REMOVES_CONTAMINANT), "sol_labels": SOLUTION_LABELS},
    )
    solutions = _uniq([r[0] for r in gas_rows])
    materials = _uniq([r[1] for r in gas_rows])

    measurements: list[str] = []
    if solutions:
        measurements = _uniq(
            [
                r[0]
                for r in store.rows(
                    "MATCH (m:Node)-[r:Rel]-(sol:Node) "
                    "WHERE r.type=$rel AND m.label='Measurement' AND sol.id IN $sols "
                    "RETURN DISTINCT m.id",
                    {"rel": str(RelType.ABOUT_REGIME), "sols": solutions},
                )
            ]
        )

    return _build_result(
        store,
        scenario="so2_removal_methods",
        solutions=solutions,
        measurements=measurements,
        materials=materials,
    )


# =====================================================================
# 6) Cold-climate heap leaching — knowledge-gap scenario
# =====================================================================
def cold_climate_heap_leaching(store: KuzuGraphStore) -> dict[str, Any]:
    """Cold-climate heap-leaching regimes and the knowledge gap around them.

    Finds ``ProcessingRegime`` nodes for heap leaching in a cold climate, the
    ``Gap`` nodes about them (``ABOUT_REGIME``) and the ``Material`` they apply to
    (``APPLIES_TO``). This scenario is expected to surface a gap rather than a
    fully-supported answer.
    """
    regimes = _uniq(
        [
            r[0]
            for r in store.rows(
                "MATCH (reg:Node) WHERE reg.label='ProcessingRegime' "
                "AND reg.operation='heap_leaching' AND reg.climate_zone='cold' "
                "RETURN DISTINCT reg.id"
            )
        ]
    )
    gaps: list[str] = []
    materials: list[str] = []
    if regimes:
        gaps = _uniq(
            [
                r[0]
                for r in store.rows(
                    "MATCH (g:Node)-[r:Rel]-(reg:Node) "
                    "WHERE r.type=$rel AND g.label='Gap' AND reg.id IN $regs "
                    "RETURN DISTINCT g.id",
                    {"rel": str(RelType.ABOUT_REGIME), "regs": regimes},
                )
            ]
        )
        materials = _uniq(
            [
                r[0]
                for r in store.rows(
                    "MATCH (reg:Node)-[r:Rel]-(mat:Node) "
                    "WHERE r.type=$rel AND mat.label='Material' AND reg.id IN $regs "
                    "RETURN DISTINCT mat.id",
                    {"rel": str(RelType.APPLIES_TO), "regs": regimes},
                )
            ]
        )
    return _build_result(
        store,
        scenario="cold_climate_heap_leaching",
        solutions=regimes,
        materials=materials,
        gaps=gaps,
    )
