"""Graph Explorer node/edge hover tooltip payloads (§5.2.3 / §17.8).

Чистые билдеры (pure, no DB, no I/O): на вход — один уже закодированный
:class:`GraphNode` / :class:`GraphEdge` ``dict`` (выход ``graph_dto``, camelCase-ключи
``evidenceCount`` / ``verified`` / ``missingFields`` / ``confidence`` / ``type`` /
``label``), на выход — компактный hover-tooltip payload для Graph Explorer.

Node tooltip (§5.2.3): заголовок (``name``/``label``), ``type``, ``evidenceCount``
(размер узла), ``verified`` (lock icon), ``missingFields`` (hollow node). Edge tooltip:
``relationType`` (из ``type``/``label``), ``confidence`` (opacity), ``sourceCount``
(число источников — ``len(evidenceIds)`` или ``evidenceCount``).

Pure builders turning one encoded GraphNode/GraphEdge dict into the §5.2.3 hover payload.

Kuzu note: custom node props are NOT queryable columns — a retriever RETURNs base columns
and reads the rest via ``get_node``; by the time a dict reaches this module it already
carries the merged, camelCase-encoded props, so nothing here touches the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _is_missing(value: Any) -> bool:
    """True if a value is absent for tooltip purposes (None or empty container)."""
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, dict, set)):
        return len(value) == 0
    return False


def _first_str(source: dict[str, Any], *keys: str) -> str:
    """First non-missing value among ``keys``, coerced to ``str`` (else empty)."""
    for key in keys:
        value = source.get(key)
        if not _is_missing(value):
            return str(value)
    return ""


def _as_int(value: Any) -> int | None:
    """Coerce to ``int`` or ``None`` (never raises)."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    """Coerce to ``float`` or ``None`` (never raises)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class NodeTooltip:
    """One §5.2.3 node hover tooltip (title, type, evidence, verified, gaps)."""

    title: str
    type: str
    evidence_count: int
    verified: bool
    missing_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.2.3 node tooltip camelCase payload (copies list)."""
        return {
            "title": self.title,
            "type": self.type,
            "evidenceCount": self.evidence_count,
            "verified": self.verified,
            "missingFields": list(self.missing_fields),
        }


@dataclass(frozen=True)
class EdgeTooltip:
    """One §5.2.3 edge hover tooltip (relation type, confidence, source count)."""

    relation_type: str
    confidence: float | None
    source_count: int

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the §5.2.3 edge tooltip camelCase payload."""
        return {
            "relationType": self.relation_type,
            "confidence": self.confidence,
            "sourceCount": self.source_count,
        }


def node_tooltip(node: dict[str, Any]) -> NodeTooltip:
    """Build the §5.2.3 node hover tooltip from one encoded GraphNode ``dict``.

    Title is the human ``label``/``name`` (falling back to ``id``); ``type`` is the
    NodeLabel; ``evidenceCount`` (absent → ``0``) drives node size; ``verified`` lights the
    lock icon; ``missingFields`` (absent → empty) renders the hollow node.
    """
    raw_missing = node.get("missingFields")
    if raw_missing is None:
        raw_missing = node.get("missing_fields")
    missing = tuple(str(x) for x in raw_missing) if raw_missing else ()
    evidence = _as_int(node.get("evidenceCount"))
    if evidence is None:
        evidence = _as_int(node.get("evidence_count"))
    return NodeTooltip(
        title=_first_str(node, "label", "name", "id"),
        type=_first_str(node, "type"),
        evidence_count=evidence if evidence is not None else 0,
        verified=bool(node.get("verified")),
        missing_fields=missing,
    )


def edge_tooltip(edge: dict[str, Any]) -> EdgeTooltip:
    """Build the §5.2.3 edge hover tooltip from one encoded GraphEdge ``dict``.

    ``relationType`` is the RelType (``type`` falling back to ``label``); ``confidence``
    (absent → ``None``) drives opacity; ``sourceCount`` is the number of backing sources —
    ``len(evidenceIds)`` when present, else the explicit ``evidenceCount`` (else ``0``).
    """
    raw_ids = edge.get("evidenceIds")
    if raw_ids is None:
        raw_ids = edge.get("evidence_ids")
    if raw_ids:
        source_count = len(raw_ids)
    else:
        count = _as_int(edge.get("evidenceCount"))
        if count is None:
            count = _as_int(edge.get("evidence_count"))
        source_count = count if count is not None else 0
    return EdgeTooltip(
        relation_type=_first_str(edge, "type", "label"),
        confidence=_as_float(edge.get("confidence")),
        source_count=source_count,
    )
