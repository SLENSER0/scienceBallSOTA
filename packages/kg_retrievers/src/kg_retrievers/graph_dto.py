"""Node/edge → frontend graph payload DTO with visual-encoding fields (§3.14/§5.2.3).

Конвертер результатов графа (узлы/рёбра) в frontend graph payload для Reagraph
(§5.3). Это чистый, детерминированный слой (no DB, no I/O): на вход — обычные
``dict`` узлов/рёбер (уже прочитанные из графа), на выход — JSON-ready ``dict`` с
camelCase-ключами, совпадающими с TS-типами фронтенда и Pydantic-DTO
``kg_common.dto`` (:class:`GraphNode` / :class:`GraphEdge` / :class:`GraphResponse`).

Visual-encoding (§5.2.3): у узла ``evidenceCount`` (размер), ``verified`` (lock
icon, из ``review_status``), ``missingFields`` (hollow node); у ребра ``confidence``
(opacity), ``evidenceCount`` (толщина), ``inferred`` (dashed), ``contradicted`` (red,
из ``CONTRADICTS``), ``evidenceIds`` (§3.7).

Kuzu note: custom node props are NOT queryable columns — a retriever must RETURN base
columns and read the rest via ``get_node``; by the time a node/edge ``dict`` reaches
this module it already carries the merged props, so nothing here touches the store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# review_status values that light the frontend "verified" lock icon (§3.7/§5.2.3).
# Mirrors KuzuGraphStore.is_reviewed ({accepted, corrected}); "verified" kept as a
# permissive legacy alias so a node literally tagged review_status="verified" counts.
VERIFIED_STATUSES: frozenset[str] = frozenset({"accepted", "corrected", "verified"})

# RelType whose presence marks a contradicting edge (§8.2 CONTRADICTS → red, §5.2.3).
CONTRADICTS_TYPE = "CONTRADICTS"

# Required props per §5.3 GraphNode type — a node missing any of these renders hollow
# (§5.2.3 "missingFields непусто → hollow node"). Unlisted types have no obligation.
REQUIRED_PROPS: dict[str, tuple[str, ...]] = {
    "Material": ("name",),
    "Experiment": ("name",),
    "ProcessingRegime": ("name",),
    "Property": ("name",),
    "Equipment": ("name",),
    "Paper": ("name",),
    "Claim": ("name",),
    "Lab": ("name",),
    "Person": ("name",),
    "Gap": ("name",),
    "Measurement": ("value", "unit"),
}

# Node keys mapped to dedicated DTO fields (in snake or camel form) — everything else
# is swept into ``properties``. Includes the raw-store "label"→type and "props" blob.
_RESERVED_NODE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "label",
        "type",
        "name",
        "review_status",
        "confidence",
        "evidence_count",
        "evidenceCount",
        "evidence_ids",
        "evidenceIds",
        "verified",
        "missing_fields",
        "missingFields",
        "community_id",
        "communityId",
        "properties",
        "props",
    }
)


def _is_missing(value: Any) -> bool:
    """True if a prop is absent for completeness purposes (None or empty container)."""
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, dict, set)):
        return len(value) == 0
    return False


def _lookup(node: dict[str, Any], key: str) -> Any:
    """Read ``key`` from the node top-level, falling back to a nested ``properties``."""
    if key in node and node[key] is not None:
        return node[key]
    inner = node.get("properties")
    if isinstance(inner, dict):
        return inner.get(key)
    return None


def _first_str(node: dict[str, Any], *keys: str) -> str:
    """First non-missing value among ``keys`` (top-level or nested), coerced to str."""
    for key in keys:
        value = _lookup(node, key)
        if not _is_missing(value):
            return str(value)
    return ""


def _as_float(value: Any) -> float | None:
    """Coerce to ``float`` or ``None`` (never raises)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    """Coerce to ``int`` or ``None`` (never raises)."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_ids(raw: Any) -> list[str]:
    """Parse an ``evidence_ids`` value (list / JSON-string / scalar / None) into ids."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x) for x in raw if x]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return [raw]
        if isinstance(parsed, list):
            return [str(x) for x in parsed if x]
        return [str(parsed)] if parsed else []
    return [str(raw)]


@dataclass(frozen=True)
class GraphNodeDTO:
    """One frontend :class:`GraphNode` (§5.3) with visual-encoding fields (§5.2.3)."""

    id: str
    label: str
    type: str
    confidence: float | None = None
    evidence_count: int | None = None
    verified: bool = False
    missing_fields: list[str] = field(default_factory=list)
    community_id: int | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.3 GraphNode camelCase payload (copies containers)."""
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "confidence": self.confidence,
            "evidenceCount": self.evidence_count,
            "verified": self.verified,
            "missingFields": list(self.missing_fields),
            "communityId": self.community_id,
            "properties": dict(self.properties),
        }


@dataclass(frozen=True)
class GraphEdgeDTO:
    """One frontend :class:`GraphEdge` (§5.3) with visual-encoding fields (§5.2.3)."""

    id: str
    source: str
    target: str
    label: str
    type: str
    confidence: float | None = None
    evidence_count: int | None = None
    inferred: bool = False
    contradicted: bool = False
    evidence_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.3 GraphEdge camelCase payload (copies containers)."""
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "type": self.type,
            "confidence": self.confidence,
            "evidenceCount": self.evidence_count,
            "inferred": self.inferred,
            "contradicted": self.contradicted,
            "evidenceIds": list(self.evidence_ids),
        }


def _node_missing_fields(node: dict[str, Any], node_type: str) -> list[str]:
    """Missing required props for ``node`` (explicit passthrough wins, else §5.3 table)."""
    explicit = node.get("missing_fields")
    if explicit is None:
        explicit = node.get("missingFields")
    if explicit is not None:
        return [str(x) for x in explicit]
    required = REQUIRED_PROPS.get(node_type, ())
    return [f for f in required if _is_missing(_lookup(node, f))]


def _node_properties(node: dict[str, Any]) -> dict[str, Any]:
    """Collect non-reserved props into the DTO ``properties`` bag (explicit wins)."""
    props: dict[str, Any] = {}
    explicit = node.get("properties")
    if isinstance(explicit, dict):
        props.update(explicit)
    for key, value in node.items():
        if key in _RESERVED_NODE_KEYS or value is None:
            continue
        props.setdefault(key, value)
    return props


def _node_evidence_count(node: dict[str, Any]) -> int | None:
    """Node ``evidenceCount``: explicit count, else the size of any ``evidence_ids``."""
    explicit = _as_int(_lookup(node, "evidence_count"))
    if explicit is not None:
        return explicit
    raw_ids = _lookup(node, "evidence_ids")
    if raw_ids is not None:
        return len(_parse_ids(raw_ids))
    return None


def node_to_dto(node: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw graph node ``dict`` to the §5.3 GraphNode payload (§5.2.3 encoding).

    Mapping: the raw store ``label`` column carries the NodeLabel → DTO ``type``; the
    human ``name`` → DTO display ``label`` (falling back to ``id``). ``review_status`` in
    :data:`VERIFIED_STATUSES` sets ``verified`` (lock icon); required props absent per
    :data:`REQUIRED_PROPS` populate ``missingFields`` (hollow node); ``evidenceCount``
    drives node size; leftover props go into ``properties``. Always emits the full nine
    camelCase keys (``None`` where unknown).
    """
    node_type = _first_str(node, "type", "label")
    label = _first_str(node, "name", "id")
    review_status = _lookup(node, "review_status")
    verified = review_status is not None and str(review_status) in VERIFIED_STATUSES
    dto = GraphNodeDTO(
        id=str(node.get("id") or ""),
        label=label,
        type=node_type,
        confidence=_as_float(_lookup(node, "confidence")),
        evidence_count=_node_evidence_count(node),
        verified=verified,
        missing_fields=_node_missing_fields(node, node_type),
        community_id=_as_int(_lookup(node, "community_id")),
        properties=_node_properties(node),
    )
    return dto.as_dict()


def edge_to_dto(edge: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw graph edge ``dict`` to the §5.3 GraphEdge payload (§5.2.3 encoding).

    Mapping: ``type`` is the RelType (falling back to ``label``); ``label`` is the human
    display (falling back to ``type``); a ``CONTRADICTS`` type — or an explicit truthy
    ``contradicted`` — sets ``contradicted`` (red edge); ``inferred`` (dashed) is passed
    through; ``evidenceIds`` are parsed and their count drives edge thickness. A missing
    ``id`` is synthesised as ``"{source}-{type}-{target}"``. Always emits the full ten
    camelCase keys (``None`` where unknown).
    """
    source = _first_str(edge, "source", "from", "src", "start")
    target = _first_str(edge, "target", "to", "dst", "end")
    edge_type = _first_str(edge, "type", "label")
    label = _first_str(edge, "label", "type")
    evidence_ids = _parse_ids(edge.get("evidence_ids"))
    explicit_count = _as_int(edge.get("evidence_count"))
    evidence_count = explicit_count
    if evidence_count is None and "evidence_ids" in edge:
        evidence_count = len(evidence_ids)
    edge_id = str(edge.get("id") or f"{source}-{edge_type}-{target}")
    contradicted = bool(edge.get("contradicted")) or edge_type == CONTRADICTS_TYPE
    dto = GraphEdgeDTO(
        id=edge_id,
        source=source,
        target=target,
        label=label,
        type=edge_type,
        confidence=_as_float(edge.get("confidence")),
        evidence_count=evidence_count,
        inferred=bool(edge.get("inferred")),
        contradicted=contradicted,
        evidence_ids=evidence_ids,
    )
    return dto.as_dict()


def build_graph_response(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, Any]:
    """Assemble the §5.3 GraphResponse ``{nodes, edges}`` from raw nodes/edges.

    Applies :func:`node_to_dto` / :func:`edge_to_dto` to each input; empty inputs yield
    ``{"nodes": [], "edges": []}``. ``layoutHints``/``queryContext`` (optional in §5.3)
    are populated by higher layers, not here.
    """
    return {
        "nodes": [node_to_dto(n) for n in nodes],
        "edges": [edge_to_dto(e) for e in edges],
    }
