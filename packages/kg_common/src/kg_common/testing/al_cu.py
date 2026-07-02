"""Canonical Al-Cu 2024 reference example (§23.3).

The single source for the "Al-Cu 2024 / aging 180°C 2h / hardness 145 HV"
example used across extraction, retrieval, eval and demo docs — so those
subsystems share one deterministic fixture instead of drifting copies.
"""

from __future__ import annotations

from typing import Any

from kg_common.testing.factories import (
    make_evidence_node,
    make_experiment_node,
    make_material_node,
    make_measurement_node,
)

AL_CU_REFERENCE: dict[str, Any] = {
    "material": "Al-Cu 2024",
    "regime": "aging 180C 2h",
    "property": "hardness",
    "value": 145.0,
    "unit": "HV",
    "doc_id": "paper:al-cu-2024",
    "temperature_c": 180.0,
    "duration_h": 2.0,
}


def al_cu_reference_nodes() -> list[dict[str, Any]]:
    """The reference example as a small, wired set of node dicts."""
    r = AL_CU_REFERENCE
    return [
        make_material_node(r["material"]),
        make_experiment_node(r["regime"]),
        make_measurement_node(r["property"], r["value"], r["unit"]),
        make_evidence_node(r["doc_id"]),
    ]
