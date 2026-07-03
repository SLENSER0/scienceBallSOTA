"""Inline community-report data-reference parser — ``[Data: …]`` (§11.11).

Parses GraphRAG inline provenance markers embedded *within* a community
report's ``full_content`` — e.g. ``[Data: Entities (5, 12); Relationships (3);
Reports (7)]``. Distinct from :mod:`graphrag_answer_citations`, which only
formats/parses a single trailing ``Reports (…)`` marker appended to an answer.
Pure, read-only string logic — no store access.

Разбирает встроенные провенанс-маркеры GraphRAG вида ``[Data: Entities (5, 12);
Relationships (3); Reports (7)]`` внутри полного текста отчёта сообщества.
Отличается от :mod:`graphrag_answer_citations`, который обрабатывает лишь один
завершающий маркер ``Reports (…)`` у ответа.

Rules:
- record types are case-insensitive; ids across *all* markers are merged,
  deduped and sorted ascending per type;
- ``parse_data_refs`` -> :class:`DataRefs` (``by_type`` keyed by canonical
  type name, ``n_markers`` = count of ``[Data: …]`` spans, ``total_refs`` =
  count of unique ids across all types);
- ``strip_data_refs`` -> text with every ``[Data: …]`` span removed and any
  leftover double spaces collapsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# One whole ``[Data: … ]`` span (non-greedy up to the closing bracket).
_SPAN_RE = re.compile(r"\[Data:\s*(?P<body>[^\]]*)\]", re.IGNORECASE)
# A single ``Type (ids)`` record inside a span body.
_RECORD_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
_INT_RE = re.compile(r"-?\d+")

# Canonical capitalisation for known record types (case-insensitive lookup).
_CANONICAL = {
    "entities": "Entities",
    "relationships": "Relationships",
    "reports": "Reports",
    "claims": "Claims",
    "sources": "Sources",
}


def _canonical_type(raw: str) -> str:
    """Return canonical type name; title-case unknown types as a fallback."""
    return _CANONICAL.get(raw.lower(), raw.title())


@dataclass(frozen=True)
class DataRefs:
    """Parsed inline data references from a report body (§11.11).

    - ``by_type`` — canonical record type -> sorted-unique id tuple;
    - ``n_markers`` — number of ``[Data: …]`` spans found;
    - ``total_refs`` — count of unique ids across *all* record types.
    """

    by_type: dict[str, tuple[int, ...]]
    n_markers: int
    total_refs: int

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain JSON-friendly dict (tuples -> lists)."""
        return {
            "by_type": {k: list(v) for k, v in self.by_type.items()},
            "n_markers": self.n_markers,
            "total_refs": self.total_refs,
        }

    @property
    def entity_ids(self) -> tuple[int, ...]:
        """Sorted-unique entity ids (empty if none)."""
        return self.by_type.get("Entities", ())

    @property
    def relationship_ids(self) -> tuple[int, ...]:
        """Sorted-unique relationship ids (empty if none)."""
        return self.by_type.get("Relationships", ())

    @property
    def report_ids(self) -> tuple[int, ...]:
        """Sorted-unique report ids (empty if none)."""
        return self.by_type.get("Reports", ())


def parse_data_refs(text: str) -> DataRefs:
    """Parse all ``[Data: …]`` markers in ``text`` into a :class:`DataRefs`.

    Record types are matched case-insensitively; ids are merged, deduped and
    sorted ascending per type across every marker.
    """
    collected: dict[str, set[int]] = {}
    n_markers = 0
    for span in _SPAN_RE.finditer(text):
        n_markers += 1
        for rec_type, ids_blob in _RECORD_RE.findall(span.group("body")):
            key = _canonical_type(rec_type)
            bucket = collected.setdefault(key, set())
            for token in _INT_RE.findall(ids_blob):
                bucket.add(int(token))
    by_type = {k: tuple(sorted(v)) for k, v in collected.items() if v}
    total_refs = len({rid for ids in by_type.values() for rid in ids})
    return DataRefs(by_type=by_type, n_markers=n_markers, total_refs=total_refs)


def strip_data_refs(text: str) -> str:
    """Remove every ``[Data: …]`` span, collapsing leftover double spaces."""
    stripped = _SPAN_RE.sub("", text)
    stripped = re.sub(r"  +", " ", stripped)
    return stripped.strip()
