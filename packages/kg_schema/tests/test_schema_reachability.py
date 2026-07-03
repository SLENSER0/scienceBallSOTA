"""Tests for declared-schema reachability lint (§8.2) — hand-checkable, no store."""

from __future__ import annotations

import pytest

from kg_schema.labels import NodeLabel
from kg_schema.relationships import EDGE_SCHEMA
from kg_schema.schema_reachability import (
    NODE_LABELS,
    ReachabilityReport,
    reachability_report,
    reachable_labels,
)


def test_document_reaches_structure_and_material() -> None:
    reach = reachable_labels("Document")
    # Document -HAS_SECTION-> Section -HAS_CHUNK-> Chunk (§3.5).
    assert "Section" in reach
    assert "Chunk" in reach
    # Material via Chunk -MENTIONS-> Entity and Experiment -HAS_MATERIAL-> Material.
    assert "Material" in reach


def test_root_always_in_reachable() -> None:
    for root in ("Document", "Experiment", "Unit", "Section"):
        assert root in reachable_labels(root)


def test_unknown_root_raises() -> None:
    with pytest.raises(ValueError):
        reachable_labels("NotALabel")
    with pytest.raises(ValueError):
        reachability_report("NotALabel")


def test_partition_disjoint_and_covers_all() -> None:
    report = reachability_report("Document")
    assert report.reachable.isdisjoint(report.unreachable)
    assert report.reachable | report.unreachable == NODE_LABELS
    assert frozenset(str(label) for label in NodeLabel) == NODE_LABELS


def test_document_is_source_label() -> None:
    report = reachability_report("Document")
    # No EDGE_SCHEMA row targets Document → it is a source (no incoming edge).
    assert "Document" in report.source_labels
    assert all(str(to_label) != "Document" for _f, _r, to_label in EDGE_SCHEMA)


def test_unit_is_sink_label() -> None:
    report = reachability_report("Document")
    # Unit has no outgoing declared edge (never a from-label) → sink.
    assert "Unit" in report.sink_labels
    assert all(str(from_label) != "Unit" for from_label, _r, _t in EDGE_SCHEMA)


def test_every_sink_has_no_from_row() -> None:
    report = reachability_report("Document")
    from_labels = {str(from_label) for from_label, _r, _t in EDGE_SCHEMA}
    for sink in report.sink_labels:
        assert sink not in from_labels


def test_sink_and_source_subset_of_node_labels() -> None:
    report = reachability_report("Document")
    assert report.sink_labels <= NODE_LABELS
    assert report.source_labels <= NODE_LABELS


def test_as_dict_reachable_is_sorted_list() -> None:
    d = reachability_report("Document").as_dict()
    assert isinstance(d["reachable"], list)
    assert d["reachable"] == sorted(d["reachable"])
    assert isinstance(d["unreachable"], list)
    assert d["unreachable"] == sorted(d["unreachable"])
    assert isinstance(d["sink_labels"], list)
    assert d["sink_labels"] == sorted(d["sink_labels"])
    assert d["root"] == "Document"


def test_report_is_frozen() -> None:
    report = reachability_report()
    assert isinstance(report, ReachabilityReport)
    with pytest.raises((AttributeError, TypeError)):
        report.root = "Paper"  # type: ignore[misc]


def test_default_root_is_document() -> None:
    assert reachability_report().root == "Document"
