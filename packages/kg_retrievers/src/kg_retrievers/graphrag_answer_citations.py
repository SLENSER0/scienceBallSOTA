"""GraphRAG inline citation formatting — ``[Data: Reports (…)]`` markers (§11.11).

Formats and parses GraphRAG-style inline citation markers so community answers
carry auditable, human-readable provenance back to their community reports and
source documents. Pure, read-only string/data logic — no store access.

Форматирует и разбирает встроенные маркеры цитирования GraphRAG вида
``[Data: Reports (1, 5, 8)]``, чтобы ответы сообществ несли проверяемую
провенанс-ссылку на отчёты и документы-источники.

Rules:
- ``format_citation`` — ids sorted ascending, deduped; ``''`` for an empty list;
- ``annotate_answer`` — appends the marker (space-separated) to text and stores
  sorted-unique ``report_ids`` and ``doc_ids``; no ids -> text unchanged;
- ``extract_report_ids`` — parses ids out of *all* markers, merged and sorted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MARKER_RE = re.compile(r"\[Data:\s*Reports\s*\(([^)]*)\)\]")
_INT_RE = re.compile(r"-?\d+")


@dataclass(frozen=True)
class CitedAnswer:
    """Answer text plus its resolved citation provenance (§11.11).

    - ``text`` — answer text, with the inline marker appended when ids exist;
    - ``report_ids`` — sorted-unique community report ids;
    - ``doc_ids`` — sorted-unique source document ids.
    """

    text: str
    report_ids: tuple[int, ...]
    doc_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialize to plain JSON-friendly dict (tuples -> lists)."""
        return {
            "text": self.text,
            "report_ids": list(self.report_ids),
            "doc_ids": list(self.doc_ids),
        }


def format_citation(report_ids: list[int]) -> str:
    """Format a GraphRAG citation marker; ids sorted-unique, ``''`` if empty."""
    unique = sorted(set(report_ids))
    if not unique:
        return ""
    inner = ", ".join(str(rid) for rid in unique)
    return f"[Data: Reports ({inner})]"


def annotate_answer(
    answer_text: str,
    used_community_ids: list[int],
    doc_ids: list[str],
) -> CitedAnswer:
    """Append a citation marker to ``answer_text`` and record its provenance."""
    report_ids = tuple(sorted(set(used_community_ids)))
    unique_docs = tuple(sorted(set(doc_ids)))
    marker = format_citation(list(report_ids))
    text = f"{answer_text} {marker}" if marker else answer_text
    return CitedAnswer(text=text, report_ids=report_ids, doc_ids=unique_docs)


def extract_report_ids(text: str) -> list[int]:
    """Parse report ids out of *all* markers in ``text``, merged and sorted."""
    ids: set[int] = set()
    for match in _MARKER_RE.finditer(text):
        for token in _INT_RE.findall(match.group(1)):
            ids.add(int(token))
    return sorted(ids)
