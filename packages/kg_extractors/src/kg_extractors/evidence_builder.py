"""Evidence-node construction + Measurement link spec (§6.10 / §8.3).

Строит узел :Evidence («no span → no fact», §6.10) и декларативную спецификацию
рёбер, привязывающую его к породившему факту и к исходному фрагменту документа
(§8.3). This module owns *construction* only — span grounding (verbatim substring
+ ``char_start``/``char_end``) is done upstream by
:mod:`kg_extractors.span_validator`; the offsets it resolves are carried here.

Каждый :Measurement обязан иметь ровно один :Evidence (§8.3): the returned link
spec always contains **exactly one** ``SUPPORTED_BY`` edge
(``Measurement → Evidence``) plus **exactly one** source edge — either
``Evidence → Chunk`` (``FROM_CHUNK``, для абзацев/подписей/метаданных) or
``Evidence → Table`` (``FROM_TABLE``, для ячеек таблиц).

Edge dicts follow the house ``{source, target, type, …}`` shape (cf.
``kg_common.dto.GraphEdge``) so they drop straight into the ingest writer. Pure
Python — no graph store, no LLM. Node/relationship/enum vocab is sourced from
:mod:`kg_schema` so it never drifts from the ontology (§8.1).

Kuzu note: custom Evidence props (``char_start`` etc.) are *not* queryable
columns — a Cypher ``RETURN`` exposes only base columns; read the rest via
``get_node()`` on the returned id.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from kg_schema.enums import ReviewStatus, SourceType
from kg_schema.labels import NodeLabel
from kg_schema.relationships import RelType

# Source types an Evidence span may carry (§8.3). Subset of :class:`SourceType`
# — ``manual`` is a curation-only origin and is not accepted by the builder.
VALID_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        SourceType.PARAGRAPH.value,
        SourceType.TABLE_CELL.value,
        SourceType.FIGURE_CAPTION.value,
        SourceType.METADATA.value,
    }
)

# Review statuses (§3.8) — used to validate the curation state on the node.
_VALID_REVIEW_STATUS: frozenset[str] = frozenset(s.value for s in ReviewStatus)

# The one label this builder emits.
_EVIDENCE_LABEL: str = NodeLabel.EVIDENCE.value


def _evidence_id(
    doc_id: str,
    page: int,
    source_type: str,
    char_start: int | None,
    char_end: int | None,
    table_id: str | None,
    row_index: int | None,
    col_index: int | None,
) -> str:
    """Deterministic content-addressed id ``ev:<16 hex>`` for an Evidence span.

    Same source location → same id (idempotent re-ingest); any differing anchor
    field → a different id. Not human-authored — read it back, never guess it.
    """
    parts = (doc_id, page, source_type, char_start, char_end, table_id, row_index, col_index)
    key = "|".join(str(part) for part in parts)
    # sha1 used purely as a content address for the id — not for security.
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"ev:{digest[:16]}"


@dataclass(frozen=True)
class Evidence:
    """An :Evidence node grounding a fact in a document span (§6.10 / §8.3).

    Fields
    ------
    id:
        Deterministic ``ev:<hex>`` id (see :func:`_evidence_id`).
    doc_id:
        Source document the span lives in (§8.3).
    page:
        1-based page number of the span.
    source_type:
        One of :data:`VALID_SOURCE_TYPES` — where the span was taken from.
    extractor:
        Name of the extractor that produced the span (provenance, §8.2).
    model:
        Model/backend that produced it (e.g. an OSS LLM id, or ``"rules"``).
    char_start / char_end:
        Verbatim-span offsets resolved by the span validator (``None`` when the
        origin has no character offsets, e.g. a whole table cell or metadata).
    table_id / row_index / col_index:
        Cell coordinates when ``source_type == "table_cell"`` (else ``None``).
    review_status:
        Curation state (§3.8); defaults to ``"pending"``.
    label:
        Always ``"Evidence"`` (§8.1).
    """

    id: str
    doc_id: str
    page: int
    source_type: str
    extractor: str
    model: str
    char_start: int | None = None
    char_end: int | None = None
    table_id: str | None = None
    row_index: int | None = None
    col_index: int | None = None
    review_status: str = ReviewStatus.PENDING.value
    label: str = _EVIDENCE_LABEL

    def as_dict(self) -> dict[str, Any]:
        """Full JSON/Cypher-friendly node view — every §8.3 field, incl. ``None``."""
        return {
            "id": self.id,
            "label": self.label,
            "doc_id": self.doc_id,
            "page": self.page,
            "source_type": self.source_type,
            "extractor": self.extractor,
            "model": self.model,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "table_id": self.table_id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "review_status": self.review_status,
        }

    @property
    def is_table_cell(self) -> bool:
        """True when the span comes from a table cell (→ ``FROM_TABLE``, §8.3)."""
        return self.source_type == SourceType.TABLE_CELL.value


def build_evidence(
    *,
    doc_id: str,
    page: int,
    source_type: str,
    extractor: str,
    model: str,
    char_start: int | None = None,
    char_end: int | None = None,
    table_id: str | None = None,
    row_index: int | None = None,
    col_index: int | None = None,
    review_status: str = ReviewStatus.PENDING.value,
) -> Evidence:
    """Construct one :class:`Evidence` node from a grounded span (§6.10 / §8.3).

    ``source_type`` must be one of :data:`VALID_SOURCE_TYPES` and ``review_status``
    a valid :class:`~kg_schema.enums.ReviewStatus` — otherwise :class:`ValueError`.
    Character offsets may be ``None`` (missing span allowed for table/metadata
    origins). The node id is content-addressed so re-ingesting the same location
    is idempotent.
    """
    st = str(source_type)
    if st not in VALID_SOURCE_TYPES:
        allowed = ", ".join(sorted(VALID_SOURCE_TYPES))
        raise ValueError(
            f"invalid source_type {source_type!r} — недопустимый source_type; "
            f"expected one of: {allowed}"
        )
    rs = str(review_status)
    if rs not in _VALID_REVIEW_STATUS:
        allowed = ", ".join(sorted(_VALID_REVIEW_STATUS))
        raise ValueError(
            f"invalid review_status {review_status!r} — недопустимый review_status; "
            f"expected one of: {allowed}"
        )
    ev_id = _evidence_id(doc_id, page, st, char_start, char_end, table_id, row_index, col_index)
    return Evidence(
        id=ev_id,
        doc_id=doc_id,
        page=page,
        source_type=st,
        extractor=extractor,
        model=model,
        char_start=char_start,
        char_end=char_end,
        table_id=table_id,
        row_index=row_index,
        col_index=col_index,
        review_status=rs,
    )


def from_table_cell(
    *,
    doc_id: str,
    page: int,
    table_id: str,
    row_index: int,
    col_index: int,
    extractor: str,
    model: str,
    char_start: int | None = None,
    char_end: int | None = None,
    review_status: str = ReviewStatus.PENDING.value,
) -> Evidence:
    """Build a ``table_cell`` :class:`Evidence`, carrying ``table_id``/row/col (§8.3).

    Convenience over :func:`build_evidence` fixing ``source_type="table_cell"`` and
    requiring the cell coordinates — these drive the ``FROM_TABLE`` edge.
    """
    return build_evidence(
        doc_id=doc_id,
        page=page,
        source_type=SourceType.TABLE_CELL.value,
        extractor=extractor,
        model=model,
        char_start=char_start,
        char_end=char_end,
        table_id=table_id,
        row_index=row_index,
        col_index=col_index,
        review_status=review_status,
    )


def _supported_by_edge(measurement_id: str, evidence: Evidence) -> dict[str, Any]:
    """``Measurement → Evidence`` ``SUPPORTED_BY`` edge (§8.3)."""
    return {
        "source": measurement_id,
        "target": evidence.id,
        "type": RelType.SUPPORTED_BY.value,
        "from_label": NodeLabel.MEASUREMENT.value,
        "to_label": _EVIDENCE_LABEL,
    }


def _source_edge(evidence: Evidence) -> dict[str, Any]:
    """``Evidence → Chunk|Table`` origin edge — ``FROM_TABLE`` for cells else ``FROM_CHUNK``."""
    if evidence.is_table_cell:
        return {
            "source": evidence.id,
            "target": evidence.table_id,
            "type": RelType.FROM_TABLE.value,
            "from_label": _EVIDENCE_LABEL,
            "to_label": NodeLabel.TABLE.value,
            "table_id": evidence.table_id,
            "row_index": evidence.row_index,
            "col_index": evidence.col_index,
        }
    return {
        "source": evidence.id,
        "target": evidence.doc_id,
        "type": RelType.FROM_CHUNK.value,
        "from_label": _EVIDENCE_LABEL,
        "to_label": NodeLabel.CHUNK.value,
        "doc_id": evidence.doc_id,
        "page": evidence.page,
        "char_start": evidence.char_start,
        "char_end": evidence.char_end,
    }


def build_evidence_for_measurement(measurement_id: str, evidence: Evidence) -> dict[str, Any]:
    """Link spec tying one :Measurement to its single :Evidence (§8.3).

    Returns the declarative edge spec enforcing «every Measurement has exactly one
    Evidence»: a lone ``SUPPORTED_BY`` edge (``Measurement → Evidence``) plus the
    Evidence's origin edge — ``FROM_TABLE`` (``→ Table``) for table cells, else
    ``FROM_CHUNK`` (``→ Chunk``). The Evidence node dict is echoed for convenience.

    Shape::

        {
          "measurement_id": ..., "evidence_id": ..., "evidence": {...},
          "supported_by": {edge}, "from_source": {edge},
          "edges": [supported_by, from_source],  # exactly one SUPPORTED_BY
        }
    """
    supported_by = _supported_by_edge(measurement_id, evidence)
    from_source = _source_edge(evidence)
    return {
        "measurement_id": measurement_id,
        "evidence_id": evidence.id,
        "evidence": evidence.as_dict(),
        "supported_by": supported_by,
        "from_source": from_source,
        "edges": [supported_by, from_source],
    }


__all__ = [
    "VALID_SOURCE_TYPES",
    "Evidence",
    "build_evidence",
    "build_evidence_for_measurement",
    "from_table_cell",
]
