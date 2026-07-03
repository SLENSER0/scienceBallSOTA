"""GraphRAG report → text-unit provenance resolver (§11.11).

A GraphRAG community *report* (отчёт сообщества) is synthesised from a set of
contributing *text units* (текстовые единицы) — the chunk-level snippets that fed
the summary. To make a report auditable (§3.6/§3.7) each contributing unit must be
traced back to the concrete document span it came from, so a claim carried by the
report can point at real evidence rather than at an opaque summary.

This module performs that join. :func:`report_to_evidence` takes a report's list of
contributing ``text_unit`` ids and resolves each one against the ``text_units``
table (rows carrying ``id``/``doc_id``/``chunk_id``/``page``/``span_start``/
``span_end``), emitting one frozen :class:`EvidenceRef` per *resolved* unit. Ids the
table does not know are silently dropped (тихо отбрасываются) — a stale report never
crashes the resolver. The ``evidence_id`` of each ref is deterministic in
``(community_id, unit_id)`` (via :func:`kg_common.uuid5_id`), so repeated resolutions
of the same report yield identical ids. :func:`distinct_doc_ids` collapses the refs
to the unique source documents in first-seen order (for de-duplicated citation
lists). Pure in-memory join — no store, no I/O, never writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger, uuid5_id

_log = get_logger("graphrag_textunit_provenance")


@dataclass(frozen=True)
class EvidenceRef:
    """One resolved text-unit → document-span reference behind a report (§11.11).

    Attributes:
        evidence_id: deterministic id derived from ``(community_id, unit_id)``
            (эвиденс-ид), identical across repeated resolutions.
        doc_id: id of the source document the unit came from (документ).
        chunk_id: id of the source chunk within the document (чанк).
        page: 1-based page the span lies on, or ``None`` when the source row
            carries no page (страница отсутствует).
        span_start: character offset the span starts at, or ``None`` when absent.
        span_end: character offset the span ends at, or ``None`` when absent.
        confidence: caller-supplied confidence stamped on the ref (уверенность).
    """

    evidence_id: str
    doc_id: str
    chunk_id: str
    page: int | None
    span_start: int | None
    span_end: int | None
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (``page``/span stay ``None`` if unset)."""
        return {
            "evidence_id": self.evidence_id,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "page": self.page,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "confidence": self.confidence,
        }


def _as_opt_int(raw: Any) -> int | None:
    """Coerce an optional integer cell (``page``/span) to ``int`` or ``None``."""
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def report_to_evidence(
    community_id: str,
    community_text_units: list[str],
    text_units: list[dict],
    *,
    confidence: float = 1.0,
) -> list[EvidenceRef]:
    """Resolve a report's contributing text-unit ids to :class:`EvidenceRef`s (§11.11).

    Joins each id in ``community_text_units`` against ``text_units`` (matched on the
    row's ``id``) and emits one ref per resolved unit, in the order the ids appear in
    the report. Each ref carries the row's ``doc_id``/``chunk_id`` and its optional
    ``page``/``span_start``/``span_end`` (missing cells stay ``None``), plus the given
    ``confidence``. The ``evidence_id`` is deterministic in ``(community_id, unit_id)``.

    An id the ``text_units`` table does not contain is silently dropped — a report
    referencing a since-deleted unit resolves to fewer refs rather than raising.
    """
    by_id = {str(row["id"]): row for row in text_units if "id" in row}
    refs: list[EvidenceRef] = []
    for unit_id in community_text_units:
        row = by_id.get(str(unit_id))
        if row is None:
            _log.info("report_to_evidence.unresolved", community_id=community_id, unit_id=unit_id)
            continue
        refs.append(
            EvidenceRef(
                evidence_id=uuid5_id("Evidence", community_id, unit_id),
                doc_id=str(row["doc_id"]),
                chunk_id=str(row["chunk_id"]),
                page=_as_opt_int(row.get("page")),
                span_start=_as_opt_int(row.get("span_start")),
                span_end=_as_opt_int(row.get("span_end")),
                confidence=confidence,
            )
        )
    return refs


def distinct_doc_ids(refs: list[EvidenceRef]) -> list[str]:
    """Return the unique ``doc_id``s across ``refs``, preserving first-seen order.

    Used to build a de-duplicated citation list — two units from the same document
    contribute the document once.
    """
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref.doc_id not in seen:
            seen.add(ref.doc_id)
            out.append(ref.doc_id)
    return out
