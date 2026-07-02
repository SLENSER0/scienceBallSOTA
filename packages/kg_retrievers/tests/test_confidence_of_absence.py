"""Confidence-of-absence for reported gaps (§25.3–25.5, §25.9)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.confidence_of_absence import (
    CONFIDENT_ABSENCE,
    COVERED,
    UNKNOWN,
    AbsenceAnalyzer,
    ExtractorRecall,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph
from kg_schema.enums import GapType

HEAP = make_id("ProcessingRegime", "cold climate heap leaching nickel")
NICKEL = make_id("Material", "nickel")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


def test_extractor_recall_resolution() -> None:
    r = ExtractorRecall(per_property={"recovery": 0.9}, per_entity_type={"Material": 0.5})
    assert r.for_property("recovery", "Material") == 0.9  # property wins
    assert r.for_property("flow_velocity", "Material") == 0.5  # falls back to entity type
    assert r.for_property("flow_velocity", "Gap") == pytest.approx(0.7)  # default


def test_confident_absence_for_cold_heap_leaching(store: KuzuGraphStore) -> None:
    # The cold-climate heap-leaching regime has no recovery Measurement, and with
    # a healthy default recall (0.7) the absence is judged real (§25.3–25.4).
    cells = AbsenceAnalyzer(store).coverage_matrix([HEAP], ["recovery"])
    assert len(cells) == 1
    cell = cells[0]
    assert cell.evidence_count == 0
    assert isinstance(cell.confidence_of_absence, float)
    assert cell.confidence_of_absence >= 0.66
    assert cell.status == CONFIDENT_ABSENCE
    # sanity: with p0=0.5, posterior for recall 0.7 is 1/(2-0.7) ≈ 0.7692
    assert cell.confidence_of_absence == pytest.approx(1 / (2 - 0.7), abs=1e-3)


def test_covered_property_has_zero_absence(store: KuzuGraphStore) -> None:
    # Nickel is reachable to a flow_velocity Measurement (via the catholyte scheme),
    # so that cell is COVERED and confidence-of-absence is 0.
    cells = AbsenceAnalyzer(store).coverage_matrix([NICKEL], ["flow_velocity"])
    cell = cells[0]
    assert cell.evidence_count >= 1
    assert cell.confidence_of_absence == 0.0
    assert cell.status == COVERED


def test_low_recall_reports_unknown(store: KuzuGraphStore) -> None:
    # If we believe the extractor barely detects a property, a null observation is
    # uninformative: the absence is "unknown", not a confident gap (§25.4).
    analyzer = AbsenceAnalyzer(store, recall=ExtractorRecall(per_property={"recovery": 0.1}))
    cell = analyzer.coverage_matrix([HEAP], ["recovery"])[0]
    assert cell.evidence_count == 0
    assert cell.confidence_of_absence == UNKNOWN
    assert cell.status == UNKNOWN


def test_scan_absence_materializes_qualified_gaps(store: KuzuGraphStore) -> None:
    analyzer = AbsenceAnalyzer(store)
    qualified = analyzer.scan_absence(domain="electrometallurgy")
    assert qualified, "expected at least one qualified absence in electrometallurgy"

    # every qualified cell is a real Gap node carrying a numeric absence_confidence
    recovery_cells = [c for c in qualified if c.property_name == "recovery"]
    assert recovery_cells, "nickel/catholyte should have no recovery data → qualified absence"
    gid = recovery_cells[0].gap_id
    assert gid is not None
    node = store.get_node(gid)
    assert node is not None
    assert node["gap_type"] == str(GapType.MISSING_PROPERTY_VALUE)
    assert isinstance(node["absence_confidence"], float)
    assert node["absence_confidence"] >= 0.66

    # the Gap is linked to its subject so retrieval can reach it
    about = store.rows(
        "MATCH (g:Node {id:$g})-[r:Rel {type:'ABOUT'}]->(m:Node) RETURN m.id",
        {"g": gid},
    )
    assert any(row[0] == recovery_cells[0].material_id for row in about)


def test_scan_absence_is_idempotent(store: KuzuGraphStore) -> None:
    AbsenceAnalyzer(store).scan_absence(domain="electrometallurgy")
    n1 = store.counts()["nodes"]
    AbsenceAnalyzer(store).scan_absence(domain="electrometallurgy")
    n2 = store.counts()["nodes"]
    # re-scanning re-uses the same Gap ids; only a fresh GapScanRun node is added
    assert n2 - n1 <= 1
