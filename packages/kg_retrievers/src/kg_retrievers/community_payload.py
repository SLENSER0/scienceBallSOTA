"""GraphRAG community-report payload schema (§11.5 / §9.8).

Каждый community report (отчёт по кластеру знаний) индексируется в Qdrant-коллекции
``graphrag_community_summaries`` (§11.5) как одна точка. This module defines the
payload schema stored alongside that point (§9.8 payload fields) plus an offline,
deterministic assembler that builds a payload from the embedded graph store.

The payload carries the §9.8 fields required by the acceptance criteria:
``community_id, level, title, rank, summary, findings, entity_ids, material_ids,
property_ids, doc_ids, build_id, build_version, created_at``. Member entity ids are
split by node label into ``material_ids`` (материалы) and ``property_ids``
(свойства); ``doc_ids`` (документы-источники) are traced through ``SUPPORTED_BY``
provenance to the backing Evidence (эвиденс) nodes.

Deterministic and offline-safe (no LLM, no clock): ``build_id``/``build_version``/
``created_at`` are always passed in explicitly by the caller (§9.8 build metadata),
never read from a wall clock here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import NodeLabel

_log = get_logger("community_payload")

# Provenance relation linking an entity to its source (§3.6); target/edge → Evidence.
_SUPPORTED_BY = "SUPPORTED_BY"
_EVIDENCE_LABEL = NodeLabel.EVIDENCE  # "Evidence"
_FINDING_LABEL = NodeLabel.FINDING  # community-summary artifact, not a member entity

# Label → payload bucket split (§9.8). Materials incl. alloys; properties standalone.
_MATERIAL_LABELS: frozenset[str] = frozenset({NodeLabel.MATERIAL, NodeLabel.ALLOY})
_PROPERTY_LABEL = NodeLabel.PROPERTY  # "Property"

# The §9.8 payload keys, in declaration order (single source of truth for (de)ser).
PAYLOAD_KEYS: tuple[str, ...] = (
    "community_id",
    "level",
    "title",
    "rank",
    "summary",
    "findings",
    "entity_ids",
    "material_ids",
    "property_ids",
    "doc_ids",
    "build_id",
    "build_version",
    "created_at",
)


@dataclass(frozen=True)
class CommunityReportPayload:
    """Qdrant payload for one GraphRAG community report (§11.5 / §9.8).

    Attributes:
        community_id: id of the community (кластер знаний) this report describes.
        level: hierarchy level of the community (0 = top / flat), for the §11.5
            ``level`` payload filter.
        title: short human title of the report.
        rank: importance score of the community (higher = more salient).
        summary: one-paragraph summary text indexed as the point's main text.
        findings: key-finding strings extracted for the community.
        entity_ids: canonical graph ids of the community's member entities.
        material_ids: subset of ``entity_ids`` labelled Material/Alloy (материалы).
        property_ids: subset of ``entity_ids`` labelled Property (свойства).
        doc_ids: source-document ids (документы) traced via SUPPORTED_BY → Evidence.
        build_id: id of the GraphRAG build that produced this report.
        build_version: version tag of that build (for ``build_version`` filtering).
        created_at: ISO timestamp when the build ran (passed in, never a live clock).
    """

    community_id: int
    level: int
    title: str
    rank: float
    summary: str
    findings: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    material_ids: list[str] = field(default_factory=list)
    property_ids: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    build_id: str = ""
    build_version: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict with the §9.8 keys (copies lists)."""
        return {
            "community_id": self.community_id,
            "level": self.level,
            "title": self.title,
            "rank": self.rank,
            "summary": self.summary,
            "findings": list(self.findings),
            "entity_ids": list(self.entity_ids),
            "material_ids": list(self.material_ids),
            "property_ids": list(self.property_ids),
            "doc_ids": list(self.doc_ids),
            "build_id": self.build_id,
            "build_version": self.build_version,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommunityReportPayload:
        """Rebuild a payload from an :meth:`as_dict` mapping (copies list fields)."""
        return cls(
            community_id=data["community_id"],
            level=data["level"],
            title=data["title"],
            rank=data["rank"],
            summary=data["summary"],
            findings=list(data.get("findings") or []),
            entity_ids=list(data.get("entity_ids") or []),
            material_ids=list(data.get("material_ids") or []),
            property_ids=list(data.get("property_ids") or []),
            doc_ids=list(data.get("doc_ids") or []),
            build_id=data.get("build_id", ""),
            build_version=data.get("build_version", ""),
            created_at=data.get("created_at", ""),
        )


def _parse_evidence_ids(raw: Any) -> list[str]:
    """Parse a rel ``evidence_ids`` value (JSON string / list / None) into ids."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return [raw]
        if isinstance(parsed, list):
            return [str(x) for x in parsed if x]
        return [str(parsed)] if parsed else []
    return []


def _split_members(
    store: KuzuGraphStore, community_id: int
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(entity_ids, material_ids, property_ids)`` for a community (§9.8).

    Members are the non-Finding nodes carrying ``community_id``; the community
    summary itself (label Finding) is a report artifact, not a member entity.
    ``label`` is a base column, so it is safe to RETURN it directly (Kuzu).
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id=$c AND n.label<>$f RETURN n.id, n.label",
        {"c": community_id, "f": str(_FINDING_LABEL)},
    )
    entity_ids: list[str] = []
    material_ids: list[str] = []
    property_ids: list[str] = []
    for nid, label in sorted(rows, key=lambda r: str(r[0])):
        if not nid:
            continue
        entity_ids.append(nid)
        if label in _MATERIAL_LABELS:
            material_ids.append(nid)
        elif label == _PROPERTY_LABEL:
            property_ids.append(nid)
    return entity_ids, material_ids, property_ids


def _gather_doc_ids(store: KuzuGraphStore, member_ids: list[str]) -> list[str]:
    """Trace SUPPORTED_BY → Evidence and collect Evidence ``doc_id`` (§9.8 / §11.11).

    An Evidence node may be the direct edge target, or referenced by the edge's
    ``evidence_ids`` property (target is a Paper/документ). Each candidate Evidence
    node is read via :meth:`KuzuGraphStore.get_node` — its ``doc_id`` is resolved
    from the node, not from the query projection.
    """
    doc_ids: set[str] = set()
    for mid in member_ids:
        rows = store.rows(
            "MATCH (m:Node {id:$id})-[r:Rel]->(t:Node) WHERE r.type=$rt "
            "RETURN t.id, t.label, r.evidence_ids",
            {"id": mid, "rt": _SUPPORTED_BY},
        )
        for t_id, t_label, edge_eids in rows:
            candidates: set[str] = set(_parse_evidence_ids(edge_eids))
            if t_label == _EVIDENCE_LABEL and t_id:
                candidates.add(t_id)
            for ev_id in candidates:
                node = store.get_node(ev_id)
                if node and node.get("label") == _EVIDENCE_LABEL:
                    doc = node.get("doc_id")
                    if doc:
                        doc_ids.add(str(doc))
    return sorted(doc_ids)


def _report_fields(
    store: KuzuGraphStore, community_id: int, *, member_count: int
) -> tuple[int, float, str, str, list[str]]:
    """Read ``(level, rank, title, summary, findings)`` from the community's Findings.

    ``detect_communities`` writes one Finding summary node per community; a build may
    attach several. ``level``/``rank`` are optional custom props read via
    :meth:`get_node` (not queryable columns in Kuzu); ``rank`` defaults to the member
    count, ``level`` to 0. ``title``/``summary`` come from the first Finding's
    ``name``/``text``; ``findings`` gathers every Finding's ``text``.
    """
    finding_ids = sorted(
        r[0]
        for r in store.rows(
            "MATCH (f:Node) WHERE f.label=$f AND f.community_id=$c RETURN f.id",
            {"f": str(_FINDING_LABEL), "c": community_id},
        )
        if r[0]
    )
    level = 0
    rank = float(member_count)
    title = ""
    summary = ""
    findings: list[str] = []
    for i, fid in enumerate(finding_ids):
        node = store.get_node(fid)
        if not node:
            continue
        text = str(node.get("text") or "")
        if text:
            findings.append(text)
        if i == 0:
            title = str(node.get("name") or "")
            summary = text
            if node.get("level") is not None:
                level = int(node["level"])
            if node.get("rank") is not None:
                rank = float(node["rank"])
    return level, rank, title, summary, findings


def build_payload(
    store: KuzuGraphStore,
    community_id: int,
    *,
    build_id: str,
    build_version: str,
    created_at: str,
) -> CommunityReportPayload:
    """Assemble the §9.8 payload for one community over a KuzuGraphStore (§11.5).

    Collects the community's member entities (splitting them into materials and
    properties by label), traces their SUPPORTED_BY provenance to Evidence source
    documents, and reads title/summary/level/rank/findings from the community's
    Finding summary node(s). An unknown/empty community yields a well-formed payload
    with empty id lists. Build metadata is supplied by the caller, never invented.
    """
    entity_ids, material_ids, property_ids = _split_members(store, community_id)
    doc_ids = _gather_doc_ids(store, entity_ids)
    level, rank, title, summary, findings = _report_fields(
        store, community_id, member_count=len(entity_ids)
    )
    payload = CommunityReportPayload(
        community_id=community_id,
        level=level,
        title=title,
        rank=rank,
        summary=summary,
        findings=findings,
        entity_ids=entity_ids,
        material_ids=material_ids,
        property_ids=property_ids,
        doc_ids=doc_ids,
        build_id=build_id,
        build_version=build_version,
        created_at=created_at,
    )
    _log.info(
        "community_payload.build",
        community_id=community_id,
        entities=len(entity_ids),
        materials=len(material_ids),
        properties=len(property_ids),
        docs=len(doc_ids),
    )
    return payload


def search_payloads(
    payloads: list[CommunityReportPayload],
    *,
    level: int | None = None,
    material_ids: list[str] | None = None,
) -> list[CommunityReportPayload]:
    """Filter payloads by ``level`` and/or ``material_ids`` (§11.5 search filters).

    Mirrors the Qdrant ``search_communities`` payload filters: an exact ``level``
    match and set-intersection membership on ``material_ids`` (a payload passes if it
    shares at least one requested material). ``None`` disables that filter; order is
    preserved.
    """
    wanted_materials = set(material_ids) if material_ids is not None else None
    out: list[CommunityReportPayload] = []
    for p in payloads:
        if level is not None and p.level != level:
            continue
        if wanted_materials is not None and not (wanted_materials & set(p.material_ids)):
            continue
        out.append(p)
    return out
