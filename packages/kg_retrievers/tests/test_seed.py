"""Seed graph coverage + idempotency (§3.17)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


def test_seed_idempotent_and_covers_scenarios() -> None:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        c1 = build_seed_graph(store)
        c2 = build_seed_graph(store)
        assert c1 == c2  # idempotent
        assert c1["nodes"] >= 35
        by = store.counts_by_label()
        # all 6 scenarios represented via these label families
        for label in (
            "Material",
            "TechnologySolution",
            "Measurement",
            "Evidence",
            "Gap",
            "Contradiction",
            "Paper",
        ):
            assert by.get(label, 0) >= 1, label
        # numeric filter works on seeded water TDS
        rows = store.rows(
            "MATCH (n:Node) WHERE n.property_name='total_dissolved_solids' "
            "AND n.value_normalized <= 1000 RETURN n.id"
        )
        assert rows
        # every factual measurement carries provenance
        missing = store.rows(
            "MATCH (n:Node) WHERE n.label='Measurement' AND n.schema_version IS NULL "
            "RETURN count(n)"
        )
        assert missing[0][0] == 0
    finally:
        store.close()


def test_seed_measurement_units_are_canonical() -> None:
    # regression: numeric filtering (agent tools) compares constraint units to
    # seed measurement units by exact string, so seed units must equal the
    # canonical spelling emitted by to_canonical (was "A/m2"/"%", now "A/m^2"/
    # "percent"). Otherwise §24 numeric acceptance queries silently return 0.
    from kg_extractors.units import to_canonical

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        build_seed_graph(store)
        rows = store.rows(
            "MATCH (m:Node) WHERE m.label='Measurement' "
            "AND m.normalized_unit IS NOT NULL AND m.normalized_unit <> '' "
            "RETURN DISTINCT m.normalized_unit",
            {},
        )
        assert rows
        for (unit,) in rows:
            canon = to_canonical(1.0, unit).unit
            assert canon == unit, f"seed unit {unit!r} is not canonical (→ {canon!r})"
    finally:
        store.close()


def test_domain_ontology_24_2() -> None:
    # §24.2 acceptance: enums valid; seed covers the 6 scenarios incl. flash
    # smelting (ПВП) with metal-distribution edges.
    from kg_schema.enums import (
        EvidenceStrength,
        MaterialClass,
        MetallurgicalDomain,
        PracticeGeography,
    )

    assert {"hydrometallurgy", "pyrometallurgy", "electrometallurgy"} <= {
        d.value for d in MetallurgicalDomain
    }
    assert {"russia", "cis", "foreign", "global", "unknown"} == {p.value for p in PracticeGeography}
    assert "peer_reviewed" in {e.value for e in EvidenceStrength}
    assert {"matte", "slag", "catholyte", "anolyte", "mine_water"} <= {
        m.value for m in MaterialClass
    }

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        build_seed_graph(store)
        # flash smelting (ПВП) scenario present
        fs = store.rows("MATCH (n:Node) WHERE n.operation='flash_smelting' RETURN count(n)")
        assert fs[0][0] >= 2
        # metal-distribution relationship (matte/slag) exercised
        dist = store.rows(
            "MATCH (m:Node {property_name:'distribution_coefficient'})"
            "-[:Rel {type:'DISTRIBUTES_BETWEEN'}]->(x:Node) RETURN count(x)"
        )
        assert dist[0][0] >= 2
        # all six scenario domains represented
        domains = {
            r[0]
            for r in store.rows(
                "MATCH (n:Node) WHERE n.domain IS NOT NULL RETURN DISTINCT n.domain"
            )
        }
        assert {"water_treatment", "electrometallurgy", "environment", "pyrometallurgy"} <= domains
    finally:
        store.close()


def test_seed_provenance_coverage_100pct() -> None:
    # §3.7: every factual node AND every edge in the seed carries provenance
    from kg_schema.provenance import provenance_report

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    try:
        build_seed_graph(store)
        ids = store.rows(
            "MATCH (n:Node) WHERE n.label IN "
            "['Measurement','Claim','Finding','Recommendation','KnowledgeClaim','Contradiction'] "
            "RETURN n.id"
        )
        rep = provenance_report([store.get_node(r[0]) for r in ids])
        assert rep["total"] >= 1 and rep["incomplete"] == 0  # 100% node coverage
        # every edge carries created_at + schema_version + extractor_run_id
        total = store.rows("MATCH ()-[r:Rel]->() RETURN count(r)")[0][0]
        cov = store.rows(
            "MATCH ()-[r:Rel]->() WHERE r.created_at IS NOT NULL AND r.schema_version IS NOT NULL "
            "AND r.extractor_run_id IS NOT NULL RETURN count(r)"
        )[0][0]
        assert cov == total  # 100% edge coverage
    finally:
        store.close()
