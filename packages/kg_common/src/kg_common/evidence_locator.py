"""Evidence-first node model — локатор доказательства (§3.6).

Every claim, value or relation in the graph carries a *locator* pointing back
into a source document — «каждый факт указывает на своё доказательство». The
Evidence Inspector and ``GET /evidence/{id}`` render this locator, so it needs a
stable, JSON-friendly shape that survives round-tripping through the store.

An :class:`EvidenceLocator` is a frozen DTO addressing a span of a document:

* text spans (``paragraph`` / ``figure_caption``) use ``char_start``/``char_end``
  and optionally a ``page`` — «текстовый спан адресуется смещениями символов».
* table cells (``table_cell``) use ``table_id`` + ``row_index`` + ``col_index``
  — «ячейка таблицы адресуется идентификатором таблицы и координатами».

Because Kuzu stores custom node props opaquely (they are not queryable columns),
the locator is always serialised via :meth:`EvidenceLocator.as_dict`, which
omits ``None`` keys so the persisted blob stays minimal.

Public API:

* :class:`EvidenceLocator`  — frozen DTO with :meth:`~EvidenceLocator.as_dict`
  and :meth:`~EvidenceLocator.key`.
* :func:`from_evidence`      — build a locator from a raw evidence mapping.
* :func:`validate_locator`   — structural validation → ``(ok, errors)``.
* :func:`same_span`          — do two locators address the same span?
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

__all__ = [
    "EvidenceLocator",
    "from_evidence",
    "same_span",
    "validate_locator",
]

# Source types that address a text span via char offsets — текстовые спаны.
_TEXT_SPAN_TYPES = frozenset({"paragraph", "figure_caption"})
# Source type addressing a table cell — ячейка таблицы.
_TABLE_CELL_TYPE = "table_cell"


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    """Immutable pointer into a source document — неизменяемый локатор (§3.6).

    ``doc_id`` and ``source_type`` are always present; the remaining fields are
    optional and only meaningful for their respective ``source_type``.
    """

    doc_id: str
    source_type: str
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    table_id: str | None = None
    row_index: int | None = None
    col_index: int | None = None

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view omitting ``None`` keys — словарь без пустых (§3.6)."""
        out: dict[str, object] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is not None:
                out[f.name] = value
        return out

    def key(self) -> str:
        """Stable dedup key for the locator — стабильный ключ (§3.6).

        Composes every addressing field (``None`` rendered as empty) so two
        locators sharing a key address the same span of the same document.
        """
        parts = [
            self.doc_id,
            self.source_type,
            "" if self.page is None else str(self.page),
            "" if self.char_start is None else str(self.char_start),
            "" if self.char_end is None else str(self.char_end),
            "" if self.table_id is None else self.table_id,
            "" if self.row_index is None else str(self.row_index),
            "" if self.col_index is None else str(self.col_index),
        ]
        return "|".join(parts)


def from_evidence(ev: Mapping[str, object]) -> EvidenceLocator:
    """Build a locator from a raw evidence mapping — из сырого доказательства (§3.6).

    Only the recognised addressing keys are consumed; extras are ignored so the
    same evidence blob may carry unrelated metadata. ``doc_id`` and
    ``source_type`` default to empty strings when absent.
    """

    def _int(key: str) -> int | None:
        value = ev.get(key)
        return None if value is None else int(value)  # type: ignore[arg-type]

    def _str(key: str) -> str | None:
        value = ev.get(key)
        return None if value is None else str(value)

    return EvidenceLocator(
        doc_id=str(ev.get("doc_id", "")),
        source_type=str(ev.get("source_type", "")),
        page=_int("page"),
        char_start=_int("char_start"),
        char_end=_int("char_end"),
        table_id=_str("table_id"),
        row_index=_int("row_index"),
        col_index=_int("col_index"),
    )


def validate_locator(loc: EvidenceLocator) -> tuple[bool, list[str]]:
    """Structural validation of a locator — структурная проверка (§3.6).

    Returns ``(ok, errors)`` where ``errors`` is a list of human-readable
    reasons. Rules:

    * ``doc_id`` and ``source_type`` must be non-empty.
    * text spans (``paragraph`` / ``figure_caption``) require both offsets with
      ``char_start < char_end`` — «начало строго меньше конца».
    * ``table_cell`` requires ``table_id`` plus ``row_index`` and ``col_index``.
    """
    errors: list[str] = []
    if not loc.doc_id:
        errors.append("doc_id is required")
    if not loc.source_type:
        errors.append("source_type is required")

    if loc.source_type in _TEXT_SPAN_TYPES:
        if loc.char_start is None or loc.char_end is None:
            errors.append("text span requires char_start and char_end")
        elif loc.char_start >= loc.char_end:
            errors.append("text span requires char_start < char_end")
    elif loc.source_type == _TABLE_CELL_TYPE:
        if loc.table_id is None:
            errors.append("table_cell requires table_id")
        if loc.row_index is None:
            errors.append("table_cell requires row_index")
        if loc.col_index is None:
            errors.append("table_cell requires col_index")

    return (not errors, errors)


def same_span(a: EvidenceLocator, b: EvidenceLocator) -> bool:
    """Do two locators address the same span? — один ли это спан? (§3.6).

    Two locators match iff their dedup :meth:`EvidenceLocator.key` are equal.
    """
    return a.key() == b.key()
