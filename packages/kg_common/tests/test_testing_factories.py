"""Test factories + canonical fixture (§23.3)."""

from __future__ import annotations

from kg_common.dto import ChatStreamEvent, EvidenceRef, GraphResponse
from kg_common.testing import (
    AL_CU_REFERENCE,
    al_cu_reference_nodes,
    make_chat_event,
    make_evidence_ref,
    make_graph_edge,
    make_graph_response,
    make_material_node,
    make_measurement_node,
)


def test_node_builders_are_valid_and_deterministic() -> None:
    a = make_material_node("Al-Cu 2024")
    b = make_material_node("Al-Cu 2024")
    assert a == b and a["id"].startswith("material:") and a["label"] == "Material"
    m = make_measurement_node("hardness", 145.0, "HV")
    assert m["value_normalized"] == 145.0 and m["normalized_unit"] == "HV"


def test_override_kwargs_win() -> None:
    n = make_material_node("steel 12Х18Н10Т", review_status="accepted", domain="metallurgy")
    assert n["review_status"] == "accepted" and n["domain"] == "metallurgy"


def test_dto_builders_validate() -> None:
    assert isinstance(make_evidence_ref(), EvidenceRef)
    edge = make_graph_edge("a", "b", "OF_PROPERTY")
    resp = make_graph_response([make_material_node()], [edge])
    assert isinstance(resp, GraphResponse) and resp.nodes and resp.edges
    ev = make_chat_event("evidence", refs=["ev:1"])
    assert isinstance(ev, ChatStreamEvent) and ev.type == "evidence"


def test_al_cu_reference_is_wired() -> None:
    nodes = al_cu_reference_nodes()
    labels = {n["label"] for n in nodes}
    assert {"Material", "Experiment", "Measurement", "Evidence"} <= labels
    meas = next(n for n in nodes if n["label"] == "Measurement")
    assert meas["value_normalized"] == AL_CU_REFERENCE["value"]
