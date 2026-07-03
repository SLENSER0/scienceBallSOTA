"""Evidence-first node integrity scan (§8.3 acceptance rule).

Каждый фактический узел должен опираться на доказательство / every factual node
(:Measurement, :Claim, :Finding) must be backed by :Evidence. The §8.3 acceptance
rule is satisfied for a factual node when there is an incident ``SUPPORTED_BY`` or
``SUPPORTS`` edge — in either direction — whose other endpoint is an :Evidence node.

This module reads a :class:`KuzuGraphStore` (never writes) and returns a frozen
:class:`EvidenceIntegrityReport` listing every factual node that fails the rule,
with per-label counts and an evidence-coverage ratio.

Kuzu note: custom node props are not queryable columns, so we RETURN only the base
``id`` / ``label`` columns; anything else would be read via ``store.get_node``.
Support is decided by joining the factual-node set against the endpoints of the
``SUPPORTED_BY`` / ``SUPPORTS`` edges — reliable on empty and disconnected graphs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore

#: Метки фактических узлов / labels whose nodes must be evidence-backed (§8.3).
FACTUAL_LABELS: frozenset[str] = frozenset({"Measurement", "Claim", "Finding"})

#: Метка узла-доказательства / the label marking an evidence node.
_EVIDENCE_LABEL = "Evidence"

#: Рёбра, несущие поддержку / edge types that carry evidential support.
_SUPPORT_TYPES = ["SUPPORTED_BY", "SUPPORTS"]

_ALL_NODES = "MATCH (n:Node) RETURN n.id, n.label"
_SUPPORT_EDGES = "MATCH (a:Node)-[r:Rel]->(b:Node) WHERE r.type IN $types RETURN a.id, b.id"


@dataclass(frozen=True)
class UnsupportedNode:
    """A factual node with no backing evidence (§8.3).

    ``node_id`` — идентификатор узла / the node id;
    ``label`` — его метка / its ontology label (a member of :data:`FACTUAL_LABELS`).
    """

    node_id: str
    label: str

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "label": self.label}


@dataclass(frozen=True)
class EvidenceIntegrityReport:
    """Result of an evidence-first integrity scan (§8.3).

    ``checked`` — число проверенных фактических узлов / factual nodes examined;
    ``unsupported`` — узлы без доказательства / nodes failing the acceptance rule;
    ``by_label`` — их распределение по меткам / per-label breakdown of failures.
    """

    checked: int
    unsupported: tuple[UnsupportedNode, ...]
    by_label: dict[str, int]

    @property
    def ok(self) -> bool:
        """True, когда все фактические узлы подкреплены / no node fails the rule."""
        return not self.unsupported

    @property
    def coverage(self) -> float:
        """Доля подкреплённых узлов / supported-over-checked, 1.0 when nothing checked."""
        if self.checked == 0:
            return 1.0
        return (self.checked - len(self.unsupported)) / self.checked

    def as_dict(self) -> dict:
        return {
            "checked": self.checked,
            "unsupported": [u.as_dict() for u in self.unsupported],
            "by_label": dict(self.by_label),
            "ok": self.ok,
            "coverage": self.coverage,
        }


def _evidence_backed_ids(store: KuzuGraphStore) -> set[str]:
    """Ids of nodes with an incident support edge to an :Evidence node (either way)."""
    evidence_ids = {nid for nid, label in store.rows(_ALL_NODES) if label == _EVIDENCE_LABEL}
    backed: set[str] = set()
    for src, dst in store.rows(_SUPPORT_EDGES, {"types": _SUPPORT_TYPES}):
        if dst in evidence_ids:
            backed.add(src)
        if src in evidence_ids:
            backed.add(dst)
    return backed


def scan_evidence_integrity(
    store: KuzuGraphStore, *, labels: frozenset[str] | None = None
) -> EvidenceIntegrityReport:
    """Scan ``store`` for factual nodes lacking backing evidence (§8.3).

    ``labels`` — если задан, заменяет :data:`FACTUAL_LABELS` / when given, overrides
    which labels count as factual (must still be evidence-backed to pass).
    """
    factual = FACTUAL_LABELS if labels is None else labels
    backed = _evidence_backed_ids(store)
    checked = 0
    unsupported: list[UnsupportedNode] = []
    by_label: Counter[str] = Counter()
    for nid, label in store.rows(_ALL_NODES):
        if label not in factual:
            continue
        checked += 1
        if nid not in backed:
            unsupported.append(UnsupportedNode(node_id=nid, label=label))
            by_label[label] += 1
    unsupported.sort(key=lambda u: u.node_id)
    return EvidenceIntegrityReport(
        checked=checked,
        unsupported=tuple(unsupported),
        by_label=dict(sorted(by_label.items())),
    )
