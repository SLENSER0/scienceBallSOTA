"""Whole-store edge-signature validation (§8.2 / §3.16).

Страж :mod:`kg_schema.edge_guard` принуждает сигнатуру ``(from_label, rel_type, to_label)``
при *записи* одного ребра, но уже наполненный граф может содержать связи, созданные до
включения проверки или в обход слоя upsert. Этот модуль — *read-only* аудит: он сканирует
каждое ребро :class:`KuzuGraphStore` и сверяет конкретную тройку меток с объявленной
:data:`kg_schema.relationships.EDGE_SCHEMA` через
:func:`kg_schema.edge_guard.is_allowed_signature` (виртуальная метка ``Entity``
разворачивается там же, где и в ``is_valid_edge``).

A whole-store, read-only validator. It reads label triples from base columns only
(``a.label``, ``r.type``, ``b.label``) — Kuzu note: кастомные свойства узла НЕ являются
запрашиваемыми колонками, но ``label``/``type`` входят в базовые колонки таблиц ``Node``/
``Rel``, поэтому доступны напрямую в ``RETURN``. Каждая недопустимая тройка возвращается
как :class:`EdgeViolation`; агрегат :class:`EdgeSignatureAudit` несёт полное число рёбер и
кортеж нарушений с булевым ``ok`` (нарушений нет) и ``violation_count``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kg_schema.edge_guard import is_allowed_signature

if TYPE_CHECKING:
    from kg_retrievers.graph_store import KuzuGraphStore

# Base-column projection: every Rel row with its endpoint labels (§8.2).
_EDGE_ROWS_CYPHER = "MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id,a.label,r.type,b.id,b.label"


@dataclass(frozen=True)
class EdgeViolation:
    """A single edge whose concrete label triple is not declared (§8.2 / §3.16).

    Attributes
    ----------
    src_id / dst_id:
        Node ids of the offending edge's endpoints.
    rel_type:
        Relationship type carried by the edge (``r.type``).
    from_label / to_label:
        Concrete labels of the source and target nodes.
    """

    src_id: str
    dst_id: str
    rel_type: str
    from_label: str
    to_label: str

    def as_dict(self) -> dict[str, str]:
        """Serialise to a flat, JSON-friendly dict (§8.2)."""
        return {
            "src_id": self.src_id,
            "dst_id": self.dst_id,
            "rel_type": self.rel_type,
            "from_label": self.from_label,
            "to_label": self.to_label,
        }


@dataclass(frozen=True)
class EdgeSignatureAudit:
    """Aggregate result of a whole-store edge-signature scan (§8.2 / §3.16).

    Attributes
    ----------
    total_edges:
        Number of ``Rel`` rows scanned.
    violations:
        Tuple of :class:`EdgeViolation`, one per undeclared edge triple.
    """

    total_edges: int
    violations: tuple[EdgeViolation, ...]

    @property
    def ok(self) -> bool:
        """``True`` iff no violation was found (equivalently ``violation_count == 0``)."""
        return not self.violations

    @property
    def violation_count(self) -> int:
        """Number of undeclared edges found."""
        return len(self.violations)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict; ``violations`` is a list of dicts (§8.2)."""
        return {
            "total_edges": self.total_edges,
            "violation_count": self.violation_count,
            "ok": self.ok,
            "violations": [v.as_dict() for v in self.violations],
        }


def audit_edge_signatures(store: KuzuGraphStore) -> EdgeSignatureAudit:
    """Scan every edge in ``store`` and report undeclared label triples (§8.2 / §3.16).

    Read-only: for each ``Rel`` row it checks ``(from_label, rel_type, to_label)`` against
    :data:`EDGE_SCHEMA` via :func:`kg_schema.edge_guard.is_allowed_signature` (``Entity``
    expansion applied). ``total_edges`` counts all rows; ``violations`` collects the
    triples that are not allowed. An empty store yields ``ok`` with ``total_edges == 0``.
    """
    rows = store.rows(_EDGE_ROWS_CYPHER)
    violations: list[EdgeViolation] = []
    for src_id, from_label, rel_type, dst_id, to_label in rows:
        if not is_allowed_signature(from_label, rel_type, to_label):
            violations.append(
                EdgeViolation(
                    src_id=src_id,
                    dst_id=dst_id,
                    rel_type=rel_type,
                    from_label=from_label,
                    to_label=to_label,
                )
            )
    return EdgeSignatureAudit(total_edges=len(rows), violations=tuple(violations))


__all__ = [
    "EdgeSignatureAudit",
    "EdgeViolation",
    "audit_edge_signatures",
]
