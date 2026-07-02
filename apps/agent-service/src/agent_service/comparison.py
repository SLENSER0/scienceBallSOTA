"""Technology comparison tables (§24.13).

Builds a normalized comparison matrix over the solutions retrieved for a query:
rows = alternatives, columns = parameters (key metrics + practice + applicability),
each cell is either evidence-backed (value + unit + evidence_ids) or explicitly
marked as a gap — never a silent blank (§24.13 acceptance).
"""

from __future__ import annotations

from typing import Any

from kg_common import get_logger
from kg_extractors.query_parser import parse_query
from kg_retrievers.graph_retriever import GraphRetriever
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("comparison")

_PROP_LABELS = {
    "flow_velocity": "Скорость потока",
    "current_density": "Плотность тока",
    "recovery": "Извлечение",
    "removal_efficiency": "Эффективность удаления",
    "distribution_coefficient": "Коэф. распределения",
    "total_dissolved_solids": "TDS",
    "concentration": "Концентрация",
    "capex": "CAPEX",
    "opex": "OPEX",
}


def build_comparison(
    query: str, store: KuzuGraphStore, *, role: str = "researcher"
) -> dict[str, Any]:
    intent = parse_query(query)
    retrieval = GraphRetriever(store).retrieve(intent)

    # collect the set of properties measured across solutions → dynamic columns
    props: list[str] = []
    for s in retrieval.solutions:
        for m in s.get("measurements", []):
            p = m.get("property_name")
            if p and p not in props:
                props.append(p)

    columns = ["Решение", "Практика", *[_PROP_LABELS.get(p, p) for p in props], "Применимость"]
    rows: list[dict[str, Any]] = []
    cells_with_evidence = 0
    cells_total = 0

    for s in retrieval.solutions:
        by_prop = {m.get("property_name"): m for m in s.get("measurements", [])}
        row: dict[str, Any] = {
            "Решение": s.get("name") or s.get("id"),
            "Практика": s.get("practice_type") or "unknown",
            "Применимость": "; ".join(a for a in s.get("applicability", []) if a) or "—",
        }
        for p in props:
            col = _PROP_LABELS.get(p, p)
            cells_total += 1
            m = by_prop.get(p)
            if m and m.get("value_normalized") is not None:
                cells_with_evidence += 1
                row[col] = {
                    "value": m["value_normalized"],
                    "unit": m.get("normalized_unit"),
                    "evidence_ids": [e["id"] for e in _evidence_for(store, m.get("id"))],
                    "gap": False,
                }
            else:
                row[col] = {"gap": True}  # §24.13: mark gaps, never blank
        rows.append(row)

    return {
        "query": query,
        "columns": columns,
        "rows": rows,
        "coverage": {
            "cells_total": cells_total,
            "cells_with_evidence": cells_with_evidence,
            "solutions": len(retrieval.solutions),
        },
    }


def _evidence_for(store: KuzuGraphStore, node_id: str | None) -> list[dict]:
    if not node_id:
        return []
    rows = store.rows(
        "MATCH (n:Node {id:$id})-[:Rel]-(ev:Node) WHERE ev.label IN ['Evidence','Paper'] RETURN ev",
        {"id": node_id},
    )
    return [store._node_dict(r[0]) for r in rows]
