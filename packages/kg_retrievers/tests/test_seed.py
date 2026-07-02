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
