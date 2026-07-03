"""Citation provenance — происхождение цитат для агента (§10.10/§6.2).

When the agent surfaces an answer, each *citation* points at a source document.
Per §10.10 «to each citation add owner/lab/version/freshness», we enrich those
citations with the catalog provenance of the underlying source: who owns it, in
which lab it lives, its catalog *version* and *freshness*, and which extractor /
model produced the extracted facts (плюс review-status курирования).

The provenance is looked up in a *source index* — a mapping ``doc_id → metadata``
built from the catalog (§6.2). Enrichment is pure and non-mutating: the original
citation mapping is never touched; a shallow copy with a nested ``provenance``
key is returned instead.

Everything here is side-effect free: no I/O, no wall-clock, no globals.

Public API:

* :class:`CitationProvenance` — frozen provenance record with :meth:`as_dict`
  that drops ``None`` fields (``doc_id`` is always kept).
* :func:`enrich_citation` — merge provenance into a copy of one citation.
* :func:`enrich_all`       — enrich a sequence of citations via a source index.
* :func:`missing_provenance` — доc_ids with no entry in the source index.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "CitationProvenance",
    "enrich_citation",
    "enrich_all",
    "missing_provenance",
]


# --------------------------------------------------------------------------- #
# Provenance record — запись происхождения                                    #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CitationProvenance:
    """Catalog provenance for one citation — происхождение одной цитаты (§10.10)."""

    doc_id: str
    owner: str | None = None
    lab: str | None = None
    version: str | None = None
    freshness: str | None = None
    extractor: str | None = None
    model: str | None = None
    review_status: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Return provenance as a mapping, dropping ``None`` fields — без None.

        ``doc_id`` is always present; every other field appears only when set.
        """
        out: dict[str, str] = {"doc_id": self.doc_id}
        optional = (
            ("owner", self.owner),
            ("lab", self.lab),
            ("version", self.version),
            ("freshness", self.freshness),
            ("extractor", self.extractor),
            ("model", self.model),
            ("review_status", self.review_status),
        )
        for key, value in optional:
            if value is not None:
                out[key] = value
        return out


# --------------------------------------------------------------------------- #
# Enrichment — обогащение цитат                                               #
# --------------------------------------------------------------------------- #

#: Provenance fields read from source metadata — поля происхождения из метаданных.
_META_FIELDS: tuple[str, ...] = (
    "owner",
    "lab",
    "version",
    "freshness",
    "extractor",
    "model",
    "review_status",
)


def _provenance_from(doc_id: str, source_meta: Mapping[str, object]) -> CitationProvenance:
    """Build a :class:`CitationProvenance` from source metadata — построить запись."""
    fields: dict[str, str | None] = {}
    for key in _META_FIELDS:
        raw = source_meta.get(key)
        fields[key] = None if raw is None else str(raw)
    return CitationProvenance(doc_id=doc_id, **fields)


def enrich_citation(
    citation: Mapping[str, object],
    source_meta: Mapping[str, object],
) -> dict[str, object]:
    """Merge provenance into a copy of ``citation`` — вернуть копию с ``provenance``.

    The returned dict is a shallow copy of ``citation`` with an added
    ``"provenance"`` key holding :meth:`CitationProvenance.as_dict`. The input
    ``citation`` is never mutated. ``doc_id`` is taken from the citation (empty
    string when absent).
    """
    doc_id = str(citation.get("doc_id", ""))
    provenance = _provenance_from(doc_id, source_meta)
    enriched: dict[str, object] = dict(citation)
    enriched["provenance"] = provenance.as_dict()
    return enriched


def enrich_all(
    citations: Sequence[Mapping[str, object]],
    source_index: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Enrich each citation via ``source_index`` — обогатить список цитат.

    For each citation the source metadata is looked up by its ``doc_id``; a
    missing entry yields an empty metadata mapping (provenance carries only the
    ``doc_id``).
    """
    result: list[dict[str, object]] = []
    for citation in citations:
        doc_id = str(citation.get("doc_id", ""))
        source_meta = source_index.get(doc_id, {})
        result.append(enrich_citation(citation, source_meta))
    return result


def missing_provenance(
    citations: Sequence[Mapping[str, object]],
    source_index: Mapping[str, Mapping[str, object]],
) -> list[str]:
    """Return doc_ids with no entry in ``source_index`` — цитаты без происхождения.

    Order follows ``citations``; duplicate doc_ids are preserved as they appear.
    """
    return [
        str(citation.get("doc_id", ""))
        for citation in citations
        if str(citation.get("doc_id", "")) not in source_index
    ]
