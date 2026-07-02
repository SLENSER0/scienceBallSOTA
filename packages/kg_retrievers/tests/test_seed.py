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
