"""Tests for graph-payload row-level access redaction (§19.3).

RU: Проверки построчной редакции графового payload по правам доступа.
EN: Checks for row-level redaction of a graph payload by access rights.
"""

from __future__ import annotations

import copy

from kg_retrievers.graph_payload_redaction import (
    RedactionReport,
    redact_graph_payload,
)


def _sample_payload() -> dict:
    """Hand-checkable payload: 4 nodes (one schema-only), 3 edges (§19.3).

    Nodes: n1(src=s1 allowed), n2(src=s2 disallowed), n3(no source_id, schema),
    n4(src=s3 disallowed). Edges: e1 n1->n3 (both allowed -> kept),
    e2 n1->n2 (n2 dropped -> removed), e3 n4->n3 (n4 dropped -> removed).
    """
    return {
        "nodes": [
            {"id": "n1", "source_id": "s1", "label": "Keep"},
            {"id": "n2", "source_id": "s2", "label": "Drop"},
            {"id": "n3", "label": "SchemaOnly"},
            {"id": "n4", "source_id": "s3", "label": "Drop"},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n3"},
            {"id": "e2", "source": "n1", "target": "n2"},
            {"id": "e3", "source": "n4", "target": "n3"},
        ],
    }


def test_disallowed_source_node_removed() -> None:
    """(1) A node whose source_id is disallowed is removed."""
    payload = _sample_payload()
    new_payload, _ = redact_graph_payload(payload, frozenset({"s1"}))
    ids = {n["id"] for n in new_payload["nodes"]}
    assert "n2" not in ids
    assert "n4" not in ids


def test_edge_referencing_removed_node_removed() -> None:
    """(2) An edge referencing a removed node is removed."""
    payload = _sample_payload()
    new_payload, _ = redact_graph_payload(payload, frozenset({"s1"}))
    edge_ids = {e["id"] for e in new_payload["edges"]}
    assert "e2" not in edge_ids  # references dropped n2
    assert "e3" not in edge_ids  # references dropped n4


def test_schema_only_node_retained() -> None:
    """(3) A node with no source_id is retained."""
    payload = _sample_payload()
    new_payload, _ = redact_graph_payload(payload, frozenset({"s1"}))
    ids = {n["id"] for n in new_payload["nodes"]}
    assert "n3" in ids


def test_hidden_source_ids_sorted_distinct() -> None:
    """(4) hidden_source_ids lists the distinct removed sources sorted."""
    payload = _sample_payload()
    _, report = redact_graph_payload(payload, frozenset({"s1"}))
    assert report.hidden_source_ids == ("s2", "s3")


def test_node_count_conserved() -> None:
    """(5) kept_nodes + hidden_nodes equals the original node count."""
    payload = _sample_payload()
    original = len(payload["nodes"])
    _, report = redact_graph_payload(payload, frozenset({"s1"}))
    assert report.kept_nodes + report.hidden_nodes == original
    assert report.kept_nodes == 2  # n1 + n3
    assert report.hidden_nodes == 2  # n2 + n4


def test_original_payload_not_mutated() -> None:
    """(6) The original payload object is not mutated."""
    payload = _sample_payload()
    snapshot = copy.deepcopy(payload)
    new_payload, _ = redact_graph_payload(payload, frozenset({"s1"}))
    assert payload == snapshot
    # Mutating the result must not leak back into the input.
    new_payload["nodes"].append({"id": "zzz"})
    new_payload["nodes"][0]["label"] = "changed"
    assert payload == snapshot


def test_edge_between_allowed_nodes_retained() -> None:
    """(7) An edge between two allowed nodes is retained."""
    payload = _sample_payload()
    new_payload, report = redact_graph_payload(payload, frozenset({"s1"}))
    edge_ids = {e["id"] for e in new_payload["edges"]}
    assert "e1" in edge_ids  # n1 -> n3, both retained
    assert report.kept_edges == 1
    assert report.hidden_edges == 2


def test_report_as_dict_roundtrip() -> None:
    """(8) RedactionReport.as_dict roundtrips to an equal report."""
    report = RedactionReport(
        kept_nodes=2,
        kept_edges=1,
        hidden_nodes=2,
        hidden_edges=2,
        hidden_source_ids=("s2", "s3"),
    )
    d = report.as_dict()
    assert d == {
        "kept_nodes": 2,
        "kept_edges": 1,
        "hidden_nodes": 2,
        "hidden_edges": 2,
        "hidden_source_ids": ["s2", "s3"],
    }
    rebuilt = RedactionReport(
        kept_nodes=d["kept_nodes"],
        kept_edges=d["kept_edges"],
        hidden_nodes=d["hidden_nodes"],
        hidden_edges=d["hidden_edges"],
        hidden_source_ids=tuple(d["hidden_source_ids"]),
    )
    assert rebuilt == report


def test_all_allowed_keeps_everything() -> None:
    """Sanity: when every source is allowed, nothing is hidden (§19.3)."""
    payload = _sample_payload()
    new_payload, report = redact_graph_payload(payload, frozenset({"s1", "s2", "s3"}))
    assert len(new_payload["nodes"]) == 4
    assert len(new_payload["edges"]) == 3
    assert report.hidden_nodes == 0
    assert report.hidden_edges == 0
    assert report.hidden_source_ids == ()
