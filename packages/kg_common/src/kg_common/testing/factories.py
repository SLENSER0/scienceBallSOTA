"""Typed builders for domain node dicts + DTOs (§23.3).

Node builders return ``{id, label, **props}`` dicts ready for
``KuzuGraphStore.upsert_node``; DTO builders return validated Pydantic models.
All ids are deterministic (``make_id``) so fixtures are reproducible (§3.8).
"""

from __future__ import annotations

from typing import Any

from kg_common.dto import (
    ChatStreamEvent,
    EvidenceRef,
    GraphEdge,
    GraphNode,
    GraphResponse,
)
from kg_common.ids import evidence_id, make_id


def make_material_node(name: str = "Al-Cu 2024", **over: Any) -> dict[str, Any]:
    node = {
        "id": make_id("Material", name),
        "label": "Material",
        "name": name,
        "material_class": "alloy",
        "review_status": "unreviewed",
    }
    return {**node, **over}


def make_experiment_node(name: str = "aging 180C 2h", **over: Any) -> dict[str, Any]:
    node = {
        "id": make_id("Experiment", name),
        "label": "Experiment",
        "name": name,
        "review_status": "unreviewed",
    }
    return {**node, **over}


def make_measurement_node(
    property_name: str = "hardness",
    value: float = 145.0,
    unit: str = "HV",
    **over: Any,
) -> dict[str, Any]:
    node = {
        "id": make_id("Measurement", f"{property_name}-{value}-{unit}"),
        "label": "Measurement",
        "name": f"{property_name} {value} {unit}",
        "property_name": property_name,
        "value_normalized": float(value),
        "normalized_unit": unit,
        "review_status": "unreviewed",
    }
    return {**node, **over}


def make_evidence_node(
    doc_id: str = "paper:al-cu-2024",
    text: str = "hardness reached 145 HV after aging at 180C for 2h",
    **over: Any,
) -> dict[str, Any]:
    node = {
        "id": evidence_id(doc_id, "0:64", "run:test"),
        "label": "Evidence",
        "doc_id": doc_id,
        "text": text,
        "evidence_strength": "peer_reviewed",
        "confidence": 0.9,
        "review_status": "unreviewed",
    }
    return {**node, **over}


def make_gap_node(name: str = "Al-Cu creep gap", **over: Any) -> dict[str, Any]:
    node = {
        "id": make_id("Gap", name),
        "label": "Gap",
        "name": name,
        "gap_type": "missing_property_value",
        "review_status": "unreviewed",
    }
    return {**node, **over}


# -- DTO builders -----------------------------------------------------------
def make_evidence_ref(evidence_id_: str = "ev:1", **over: Any) -> EvidenceRef:
    data: dict[str, Any] = {
        "evidence_id": evidence_id_,
        "source_id": "paper:al-cu-2024",
        "text": "hardness 145 HV",
        "confidence": 0.9,
    }
    return EvidenceRef(**{**data, **over})


def make_graph_edge(source: str, target: str, label: str = "MEASURED", **over: Any) -> GraphEdge:
    data: dict[str, Any] = {
        "id": f"{source}->{target}:{label}",
        "source": source,
        "target": target,
        "label": label,
        "type": label,
        "confidence": 0.9,
    }
    return GraphEdge(**{**data, **over})


def make_graph_response(
    nodes: list[dict[str, Any]] | None = None, edges: list[GraphEdge] | None = None
) -> GraphResponse:
    gnodes = [
        GraphNode(id=n["id"], label=n.get("name", n["id"]), type=n["label"]) for n in (nodes or [])
    ]
    return GraphResponse(nodes=gnodes, edges=list(edges or []))


def make_chat_event(type_: str = "token", **data: Any) -> ChatStreamEvent:
    return ChatStreamEvent(type=type_, data=data)  # type: ignore[arg-type]
