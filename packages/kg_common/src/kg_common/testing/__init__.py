"""Test data factories + canonical fixtures (§23.3).

One typed way to construct valid domain objects and DTOs in any test, on top of
``kg_common`` ids/DTOs. Import from here rather than hand-rolling dicts so test
data cannot drift from the schema.
"""

from __future__ import annotations

from kg_common.testing.al_cu import AL_CU_REFERENCE, al_cu_reference_nodes
from kg_common.testing.factories import (
    make_chat_event,
    make_evidence_node,
    make_evidence_ref,
    make_experiment_node,
    make_gap_node,
    make_graph_edge,
    make_graph_response,
    make_material_node,
    make_measurement_node,
)

__all__ = [
    "make_material_node",
    "make_experiment_node",
    "make_measurement_node",
    "make_evidence_node",
    "make_gap_node",
    "make_evidence_ref",
    "make_graph_edge",
    "make_graph_response",
    "make_chat_event",
    "AL_CU_REFERENCE",
    "al_cu_reference_nodes",
]
