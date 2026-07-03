"""Agent evidence-assembler node (§13.14).

Собирает доводы (evidence) для набора узлов-фактов и превращает их в
пронумерованные ссылки-цитаты. For a set of fact node ids the node walks each
``(факт)-[:SUPPORTED_BY]->(:Evidence)`` edge directly on the ``KuzuGraphStore``,
folds the spans into deduplicated :class:`EvidenceRef`-shaped records, orders them
deterministically (сила довода → уверенность / evidence strength → confidence
desc), numbers them ``[1]``, ``[2]``, … into :class:`Citation` objects and groups
those markers by source document (документ-источник).

The result is a frozen :class:`AssembledEvidence` whose ``as_dict`` returns the
agent-facing payload ``{citations, by_document, count}`` (evidence-first, §8.3).
Nothing here is written back — the node is a pure, read-only projection over the
graph, so it stays unit-testable on a seeded temp store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kg_common import Citation, EvidenceRef

if TYPE_CHECKING:
    from kg_retrievers.graph_store import KuzuGraphStore

# Cypher: outgoing SUPPORTED_BY edges from a fact node to its Evidence spans.
# Mirrors the Evidence Inspector query (api_gateway.routers.evidence) so the agent
# and the API surface the same provenance for a node.
_SUPPORTED_BY_Q = (
    "MATCH (f:Node {id:$id})-[:Rel {type:'SUPPORTED_BY'}]->(e:Node {label:'Evidence'}) "
    "RETURN e.id, e.doc_id, e.page, e.text, e.evidence_strength, e.confidence"
)

# Evidence-strength vocabulary ranked strongest→weakest (kg_schema EvidenceStrength).
# Lower rank sorts first; an unknown/missing strength sorts after every known one.
_STRENGTH_ORDER: tuple[str, ...] = (
    "peer_reviewed",
    "patent",
    "internal_report",
    "experiment_protocol",
    "standard",
    "expert_comment",
    "unverified",
)
_STRENGTH_RANK: dict[str, int] = {s: i for i, s in enumerate(_STRENGTH_ORDER)}
_UNKNOWN_STRENGTH_RANK = len(_STRENGTH_ORDER)

# Group key for spans that carry no document id (документ неизвестен).
_NO_DOCUMENT = "(no document)"


@dataclass(frozen=True)
class AssembledEvidence:
    """Frozen result of :func:`assemble_evidence` (§13.14).

    ``citations`` are ordered, numbered :class:`Citation` objects; ``by_document``
    maps each ``doc_id`` (документ-источник) to the citation markers drawn from it;
    ``count`` is the number of deduplicated citations.
    """

    citations: tuple[Citation, ...]
    by_document: dict[str, list[str]]
    count: int

    def as_dict(self) -> dict[str, Any]:
        """Agent-facing payload: ``{citations, by_document, count}``."""
        return {
            "citations": [c.model_dump() for c in self.citations],
            "by_document": {doc: list(markers) for doc, markers in self.by_document.items()},
            "count": self.count,
        }


def _row_to_ref(row: list[Any], source_id: str) -> EvidenceRef:
    """Build an :class:`EvidenceRef` from one ``_SUPPORTED_BY_Q`` result row."""
    eid, doc_id, page, text, strength, confidence = row
    return EvidenceRef(
        evidence_id=str(eid),
        source_id=source_id,
        doc_id=doc_id,
        page=page,
        text=text,
        evidence_strength=strength,
        # EvidenceRef.confidence is a non-optional float; coalesce a missing value.
        confidence=1.0 if confidence is None else float(confidence),
    )


def _order_key(ref: EvidenceRef) -> tuple[int, float]:
    """Stable ordering: strongest evidence first, then highest confidence first."""
    rank = _STRENGTH_RANK.get(ref.evidence_strength or "", _UNKNOWN_STRENGTH_RANK)
    return (rank, -ref.confidence)


def _dedup_key(ref: EvidenceRef) -> tuple[Any, Any, Any]:
    """Two spans are the same citation when they point at the same doc/page/text."""
    return (ref.doc_id, ref.page, ref.text)


def _refs_for_node(store: KuzuGraphStore, node_id: str) -> list[EvidenceRef]:
    """All SUPPORTED_BY Evidence refs for one fact node, strongest-first."""
    refs = [_row_to_ref(row, node_id) for row in store.rows(_SUPPORTED_BY_Q, {"id": node_id})]
    refs.sort(key=_order_key)
    return refs


def assemble_evidence(
    store: KuzuGraphStore,
    node_ids: list[str],
    *,
    max_per_claim: int = 5,
) -> AssembledEvidence:
    """Assemble deduplicated, numbered citations for a set of fact node ids (§13.14).

    For every id in ``node_ids`` the strongest ``max_per_claim`` SUPPORTED_BY
    Evidence spans are taken (по каждому факту / per claim), folded into a global
    set deduplicated by ``(doc_id, page, text)``, ordered by evidence strength then
    confidence, and numbered ``[1]``, ``[2]``, … Empty ``node_ids`` yields an empty
    :class:`AssembledEvidence`.
    """
    picked: dict[tuple[Any, Any, Any], EvidenceRef] = {}
    for node_id in node_ids:
        kept = 0
        for ref in _refs_for_node(store, node_id):
            if kept >= max(0, max_per_claim):
                break
            key = _dedup_key(ref)
            if key in picked:
                continue  # same span already cited via another (or this) claim
            picked[key] = ref
            kept += 1

    ordered = sorted(picked.values(), key=_order_key)
    citations: list[Citation] = []
    by_document: dict[str, list[str]] = {}
    for i, ref in enumerate(ordered, start=1):
        marker = f"[{i}]"
        title = (ref.text or ref.doc_id or ref.evidence_id)[:80]
        citations.append(Citation(marker=marker, evidence=ref, source_title=title))
        by_document.setdefault(ref.doc_id or _NO_DOCUMENT, []).append(marker)

    return AssembledEvidence(
        citations=tuple(citations),
        by_document=by_document,
        count=len(citations),
    )
