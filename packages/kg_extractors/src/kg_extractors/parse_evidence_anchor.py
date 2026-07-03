"""Parse-time evidence anchor stubs — location only (§5.7 / §8.3).

Опорные метки доказательств на этапе разбора: только местоположение.

The §8.3 *Evidence anchor* is the "where did this come from?" pointer stapled to
every extracted fact. This module builds the **stub** produced at parse time:
it records *only* the physical location of a span — which document, what kind of
surface (paragraph / table cell / figure caption) and the coordinates inside it.
It deliberately carries **no** ``extractor``, ``model`` or ``confidence`` field;
those provenance fields belong to §6 / ``evidence_builder`` and are grafted on
downstream once an extractor actually reads the anchored span.

Two coordinate systems live side by side, and each surface uses exactly one:

* **Character offsets** — ``page`` plus a half-open ``[char_start, char_end)``
  range into the page's flat text. Used by prose spans: paragraphs and figure
  captions.
* **Table coordinates** — ``table_id`` plus ``row_index`` / ``col_index``. Used
  by a single table cell; character offsets stay ``None`` because a cell has no
  meaningful flat-text range at parse time.

Public API:

- :class:`EvidenceAnchor` — frozen location stub; :meth:`EvidenceAnchor.as_dict`
  omits every ``None``-valued field so the serialized shape names only the
  coordinates that surface actually uses.
- :func:`anchor_for_paragraph` — prose span in a paragraph.
- :func:`anchor_for_table_cell` — one cell of a parsed table.
- :func:`anchor_for_caption` — prose span in a figure caption.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# The three surface kinds a parse-time anchor may point at (§8.3).
_SOURCE_TYPES = frozenset({"paragraph", "table_cell", "figure_caption"})


@dataclass(frozen=True)
class EvidenceAnchor:
    """Parse-time §8.3 evidence anchor — location of a span, nothing more.

    Опорная метка: только где находится фрагмент, без сведений об извлекателе.

    ``source_type`` picks the surface kind (one of ``paragraph``,
    ``table_cell``, ``figure_caption``). Prose surfaces populate ``page`` and the
    half-open ``[char_start, char_end)`` offsets; a table cell populates
    ``table_id`` / ``row_index`` / ``col_index`` and leaves the offsets ``None``.
    Provenance (extractor, model, confidence) is **not** stored here — that is
    ``evidence_builder``'s job (§6).
    """

    doc_id: str
    source_type: str
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    table_id: str | None = None
    row_index: int | None = None
    col_index: int | None = None

    def __post_init__(self) -> None:
        if not self.doc_id:
            raise ValueError("doc_id must be a non-empty string")
        if self.source_type not in _SOURCE_TYPES:
            allowed = ", ".join(sorted(_SOURCE_TYPES))
            raise ValueError(f"source_type must be one of {{{allowed}}}, got {self.source_type!r}")

    def as_dict(self) -> dict[str, object]:
        """Frozen mapping of the set coordinates — every ``None`` field dropped.

        Only the fields this surface actually uses appear: a paragraph anchor has
        no ``table_id`` / ``row_index`` / ``col_index`` keys, a table-cell anchor
        has no ``char_start`` / ``char_end`` keys. ``doc_id`` and ``source_type``
        are always present (they are never ``None``).
        """
        return {f.name: value for f in fields(self) if (value := getattr(self, f.name)) is not None}


def _check_char_span(char_start: int, char_end: int) -> None:
    """Validate a half-open prose span; raise :class:`ValueError` if malformed."""
    if char_start < 0:
        raise ValueError(f"char_start must be >= 0, got {char_start}")
    if char_end < char_start:
        raise ValueError(f"char_end {char_end} precedes char_start {char_start}")


def anchor_for_paragraph(
    doc_id: str,
    page: int,
    char_start: int,
    char_end: int,
) -> EvidenceAnchor:
    """Build a ``paragraph`` anchor over a half-open ``[char_start, char_end)``.

    Points at a prose span on ``page``. Raises :class:`ValueError` when
    ``char_start < 0`` or ``char_end < char_start`` (span must not run backwards).
    """
    _check_char_span(char_start, char_end)
    return EvidenceAnchor(
        doc_id=doc_id,
        source_type="paragraph",
        page=page,
        char_start=char_start,
        char_end=char_end,
    )


def anchor_for_table_cell(
    doc_id: str,
    table_id: str,
    row_index: int,
    col_index: int,
    page: int | None = None,
) -> EvidenceAnchor:
    """Build a ``table_cell`` anchor at ``(row_index, col_index)`` of ``table_id``.

    Character offsets stay ``None`` (a cell has no flat-text range); ``page`` is
    optional. Raises :class:`ValueError` when ``row_index`` or ``col_index`` is
    negative — table coordinates are zero-based and non-negative.
    """
    if row_index < 0:
        raise ValueError(f"row_index must be >= 0, got {row_index}")
    if col_index < 0:
        raise ValueError(f"col_index must be >= 0, got {col_index}")
    return EvidenceAnchor(
        doc_id=doc_id,
        source_type="table_cell",
        page=page,
        table_id=table_id,
        row_index=row_index,
        col_index=col_index,
    )


def anchor_for_caption(
    doc_id: str,
    page: int,
    char_start: int,
    char_end: int,
) -> EvidenceAnchor:
    """Build a ``figure_caption`` anchor over a half-open ``[char_start, char_end)``.

    Points at a prose span inside a figure caption on ``page``. Raises
    :class:`ValueError` when ``char_start < 0`` or ``char_end < char_start``.
    """
    _check_char_span(char_start, char_end)
    return EvidenceAnchor(
        doc_id=doc_id,
        source_type="figure_caption",
        page=page,
        char_start=char_start,
        char_end=char_end,
    )
