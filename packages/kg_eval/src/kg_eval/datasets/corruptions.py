"""[DE] Semi-synthetic corruption operators (spec §33.3, "Dataset 2").

Take a correct corpus and apply *labelled* damage whose expected system reaction is
known. The implemented vertical slice is :func:`retract_cells`, which realises the
``retracted`` reality via the soft-retraction primitive; the broader operator
catalogue is declared in :data:`OPERATOR_CATALOG` as design surface.
"""

from __future__ import annotations

from typing import Any

from kg_eval.matching import _property_name
from kg_eval.schemas import AbsenceCell, DatasetManifest
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.retractions import active_measurements, retract

# Declared-but-not-implemented operators → expected reaction. Only "retract_cells"
# has a matching callable; the rest are specification surface.
OPERATOR_CATALOG: dict[str, str] = {
    "retract_cells": "verdict flips to 'retracted' (distinct from never-measured)",
    "drop_table_keep_prose_with_value": "table row removed, prose value kept → 'possible_miss'",
    "drop_table_keep_prose_name_only": "table row removed, property only named → 'genuine_gap' (NOT possible_miss)",  # noqa: E501
    "remove_all_traces": "cell absent everywhere → 'genuine_gap'",
    "swap_unit_wrong_dimension": "validation issue 'unit_dimension' → routed to review, not accepted",  # noqa: E501
    "corrupt_value": "extracted value differs from source → Track-A value mismatch (false accept)",
    "drop_unit": "numeric without unit → validation error 'numeric_requires_unit'",
    "russian_wordform": "RU inflected surface must still link to the canonical entity",
    "transliterate_alias": "Cyrillic/Latin alias variant must link to the same material",
    "restrict_access": "restricted evidence must not leak to an unauthorised reader",
}


def _observation_ids(store: KuzuGraphStore, cell: AbsenceCell) -> set[str]:
    prop_name = _property_name(store, cell.property_id)
    return {
        m["id"]
        for m in active_measurements(store, cell.material_id, include_retracted=True)
        if m.get("property_name") == prop_name
    }


def retract_cells(
    store: KuzuGraphStore,
    manifest: DatasetManifest,
    *,
    archetype: str = "RETRACTED",
    reviewer_id: str = "benchmark",
    at: str = "2026-06-15",
) -> list[dict[str, Any]]:
    """Soft-retract every observation of each cell whose ``archetype`` matches, so its
    reality becomes ``retracted``. Idempotent (re-retracting is a no-op)."""
    done: list[dict[str, Any]] = []
    for cell in manifest.cells:
        if cell.archetype != archetype:
            continue
        for oid in sorted(_observation_ids(store, cell)):
            try:
                rec = retract(
                    store, oid, reason="benchmark corruption: retracted", actor=reviewer_id, at=at
                )
                done.append(
                    {
                        "cell": cell.key(),
                        "observation_id": oid,
                        "ok": rec is not None,
                        "result": rec,
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive
                done.append(
                    {"cell": cell.key(), "observation_id": oid, "ok": False, "error": str(exc)}
                )
    return done
