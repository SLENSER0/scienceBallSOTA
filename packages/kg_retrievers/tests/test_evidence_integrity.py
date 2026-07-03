"""Evidence-first node integrity scan tests (§8.3).

Hand-checkable graphs built per test over a fresh temp Kuzu store:

- a Measurement with a SUPPORTED_BY edge to an :Evidence node passes;
- a lone Measurement with no evidence is flagged and counted by label;
- coverage is supported / checked (0.5 for one-of-two);
- ``ok`` is True iff nothing is unsupported;
- a Claim reached by SUPPORTS *from* an :Evidence node counts as covered;
- only nodes whose label is factual are checked (a Material is ignored);
- an empty store passes with checked 0 and coverage 1.0.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.evidence_integrity import (
    FACTUAL_LABELS,
    EvidenceIntegrityReport,
    UnsupportedNode,
    scan_evidence_integrity,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def test_factual_labels_frozenset() -> None:
    assert frozenset({"Measurement", "Claim", "Finding"}) == FACTUAL_LABELS


def test_supported_measurement_not_flagged() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", name="m1")
    store.upsert_node("e1", "Evidence", name="e1")
    store.upsert_edge("m1", "e1", "SUPPORTED_BY")
    report = scan_evidence_integrity(store)
    assert report.ok is True
    assert report.checked == 1
    assert report.unsupported == ()
    assert report.coverage == 1.0


def test_lone_measurement_is_unsupported() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", name="m1")
    report = scan_evidence_integrity(store)
    assert report.checked == 1
    assert report.unsupported == (UnsupportedNode(node_id="m1", label="Measurement"),)
    assert report.by_label["Measurement"] == 1
    assert report.ok is False
    assert report.coverage == 0.0


def test_coverage_half_when_one_of_two_supported() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", name="m1")
    store.upsert_node("m2", "Measurement", name="m2")
    store.upsert_node("e1", "Evidence", name="e1")
    store.upsert_edge("m1", "e1", "SUPPORTED_BY")
    report = scan_evidence_integrity(store)
    assert report.checked == 2
    assert report.coverage == 0.5
    assert report.unsupported == (UnsupportedNode(node_id="m2", label="Measurement"),)


def test_ok_true_iff_no_unsupported() -> None:
    store = _store()
    store.upsert_node("c1", "Claim", name="c1")
    store.upsert_node("e1", "Evidence", name="e1")
    store.upsert_edge("c1", "e1", "SUPPORTED_BY")
    good = scan_evidence_integrity(store)
    assert good.ok is True
    store.upsert_node("c2", "Claim", name="c2")  # now one is unbacked
    bad = scan_evidence_integrity(store)
    assert bad.ok is False


def test_claim_supported_via_incoming_supports_edge() -> None:
    store = _store()
    store.upsert_node("c1", "Claim", name="c1")
    store.upsert_node("e1", "Evidence", name="e1")
    # Evidence -[SUPPORTS]-> Claim : incident edge, other endpoint is Evidence
    store.upsert_edge("e1", "c1", "SUPPORTS")
    report = scan_evidence_integrity(store)
    assert report.ok is True
    assert report.checked == 1
    assert report.coverage == 1.0


def test_non_factual_node_ignored() -> None:
    store = _store()
    store.upsert_node("mat1", "Material", name="steel")  # not factual -> not checked
    store.upsert_node("m1", "Measurement", name="m1")
    store.upsert_node("e1", "Evidence", name="e1")
    store.upsert_edge("m1", "e1", "SUPPORTED_BY")
    report = scan_evidence_integrity(store)
    assert report.checked == 1  # only the Measurement
    assert report.ok is True


def test_support_edge_to_non_evidence_does_not_count() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", name="m1")
    store.upsert_node("mat1", "Material", name="steel")
    # edge is a support type but the target is not an Evidence node
    store.upsert_edge("m1", "mat1", "SUPPORTED_BY")
    report = scan_evidence_integrity(store)
    assert report.ok is False
    assert report.unsupported == (UnsupportedNode(node_id="m1", label="Measurement"),)


def test_finding_supported_and_by_label_breakdown() -> None:
    store = _store()
    store.upsert_node("e1", "Evidence", name="e1")
    store.upsert_node("f1", "Finding", name="f1")
    store.upsert_edge("f1", "e1", "SUPPORTED_BY")
    store.upsert_node("f2", "Finding", name="f2")  # unbacked
    store.upsert_node("c1", "Claim", name="c1")  # unbacked
    report = scan_evidence_integrity(store)
    assert report.checked == 3
    assert report.by_label == {"Claim": 1, "Finding": 1}
    assert {u.node_id for u in report.unsupported} == {"c1", "f2"}


def test_custom_labels_override() -> None:
    store = _store()
    store.upsert_node("obs1", "Observation", name="o1")  # unbacked, custom-factual
    store.upsert_node("m1", "Measurement", name="m1")  # ignored under override
    report = scan_evidence_integrity(store, labels=frozenset({"Observation"}))
    assert report.checked == 1
    assert report.unsupported == (UnsupportedNode(node_id="obs1", label="Observation"),)


def test_empty_store_passes() -> None:
    store = _store()
    report = scan_evidence_integrity(store)
    assert isinstance(report, EvidenceIntegrityReport)
    assert report.ok is True
    assert report.checked == 0
    assert report.coverage == 1.0
    assert report.unsupported == ()


def test_report_as_dict() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", name="m1")
    report = scan_evidence_integrity(store)
    assert report.as_dict() == {
        "checked": 1,
        "unsupported": [{"node_id": "m1", "label": "Measurement"}],
        "by_label": {"Measurement": 1},
        "ok": False,
        "coverage": 0.0,
    }
