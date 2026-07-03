"""Evidence-span validator — «no span → no fact» invariant (§6.10).

Every extracted fact must carry an ``evidence_text`` that is a *verbatim*
substring of the source chunk (or, when ``fuzzy`` is enabled, a
whitespace/case-normalized match). This module confirms that grounding and
resolves the exact ``char_start`` / ``char_end`` offsets used to build the
``Evidence`` node (§8.3). Pure Python (``re``/``str`` only) so it never
depends on an LLM or optional ML stack. Works on RU + EN text (кириллица).

Status flags (флаги статуса):

- ``exact``          — span_text is a byte-for-byte substring of source_text;
- ``normalized``     — matches after collapsing whitespace + case-folding
                       (fuzzy подстрока), e.g. «МЕДНЫЙ КУПОРОС» → «медный купорос»;
- ``not_found``      — hallucinated span, no grounding → факт отклонён;
- ``offset_mismatch``— caller-supplied offsets do not contain span_text.

Public API:

- :func:`find_span` — first exact occurrence → ``(start, end)`` | ``None``;
- :func:`validate_span` — full :class:`SpanValidation` for one span;
- :func:`validate_extraction` — aggregate :class:`ExtractionReport` for many.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- status constants (§6.10) --------------------------------------------------
STATUS_EXACT = "exact"
STATUS_NORMALIZED = "normalized"
STATUS_NOT_FOUND = "not_found"
STATUS_OFFSET_MISMATCH = "offset_mismatch"

VALID_STATUSES: frozenset[str] = frozenset(
    {STATUS_EXACT, STATUS_NORMALIZED, STATUS_NOT_FOUND, STATUS_OFFSET_MISMATCH}
)
#: statuses that count as a successfully grounded span (span → fact allowed).
_OK_STATUSES: frozenset[str] = frozenset({STATUS_EXACT, STATUS_NORMALIZED})

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Whitespace-collapsed, case-folded form used for fuzzy comparison.

    Casefolding handles Cyrillic case («МЕДНЫЙ» → «медный»); whitespace runs
    (space/tab/newline) collapse to a single space and edges are stripped.
    """
    return _WS_RE.sub(" ", text.strip()).casefold()


@dataclass(frozen=True)
class SpanValidation:
    """Result of validating one evidence span against its source (§6.10)."""

    status: str
    span_text: str
    char_start: int | None = None
    char_end: int | None = None
    matched_text: str | None = None
    fuzzy_used: bool = False

    @property
    def ok(self) -> bool:
        """True when the span is grounded (``exact`` or ``normalized``)."""
        return self.status in _OK_STATUSES

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "span_text": self.span_text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "matched_text": self.matched_text,
            "fuzzy_used": self.fuzzy_used,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class ExtractionReport:
    """Aggregate span-validation report for a whole extraction (§6.10)."""

    total: int
    exact: int
    normalized: int
    not_found: int
    offset_mismatch: int
    results: tuple[SpanValidation, ...]

    @property
    def valid(self) -> int:
        """Number of grounded spans (``exact`` + ``normalized``)."""
        return self.exact + self.normalized

    @property
    def invalid(self) -> int:
        """Number of rejected spans (``not_found`` + ``offset_mismatch``)."""
        return self.not_found + self.offset_mismatch

    @property
    def all_grounded(self) -> bool:
        """True when every span is grounded (invariant holds for all facts)."""
        return self.total > 0 and self.invalid == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "exact": self.exact,
            "normalized": self.normalized,
            "not_found": self.not_found,
            "offset_mismatch": self.offset_mismatch,
            "valid": self.valid,
            "invalid": self.invalid,
            "all_grounded": self.all_grounded,
            "results": [r.as_dict() for r in self.results],
        }


def find_span(source_text: str, span_text: str) -> tuple[int, int] | None:
    """Return ``(start, end)`` of the first *exact* occurrence, else ``None``.

    An empty ``span_text`` never matches (empty span → not grounded).
    """
    if not source_text or not span_text:
        return None
    idx = source_text.find(span_text)
    if idx < 0:
        return None
    return idx, idx + len(span_text)


def _fuzzy_find(source_text: str, span_text: str) -> tuple[int, int] | None:
    """Whitespace/case-tolerant search returning offsets into *source_text*.

    Internal whitespace in the (stripped) span becomes ``\\s+`` so differing
    spacing still matches, and the search is case-insensitive (Cyrillic-aware).
    """
    core = span_text.strip()
    if not core:
        return None
    parts = _WS_RE.split(core)
    pattern = r"\s+".join(re.escape(p) for p in parts if p)
    if not pattern:
        return None
    m = re.search(pattern, source_text, re.IGNORECASE)
    if m is None:
        return None
    return m.start(), m.end()


def validate_span(
    source_text: str,
    span_text: str,
    *,
    char_start: int | None = None,
    char_end: int | None = None,
    fuzzy: bool = True,
) -> SpanValidation:
    """Validate one evidence span against ``source_text`` (§6.10).

    If ``char_start``/``char_end`` are both supplied they are checked first: a
    match yields ``exact`` (or ``normalized`` under ``fuzzy``); a disagreement
    yields ``offset_mismatch``. Otherwise the span is located by exact search,
    then — when ``fuzzy`` — by a whitespace/case-normalized search. The resolved
    offsets satisfy ``source_text[char_start:char_end] == matched_text``.
    """
    if not span_text:
        return SpanValidation(STATUS_NOT_FOUND, span_text)

    has_offsets = char_start is not None and char_end is not None
    if has_offsets:
        return _validate_with_offsets(source_text, span_text, int(char_start), int(char_end), fuzzy)

    exact = find_span(source_text, span_text)
    if exact is not None:
        start, end = exact
        return SpanValidation(STATUS_EXACT, span_text, start, end, source_text[start:end], False)

    if fuzzy:
        approx = _fuzzy_find(source_text, span_text)
        if approx is not None:
            start, end = approx
            return SpanValidation(
                STATUS_NORMALIZED, span_text, start, end, source_text[start:end], True
            )

    return SpanValidation(STATUS_NOT_FOUND, span_text)


def _validate_with_offsets(
    source_text: str,
    span_text: str,
    char_start: int,
    char_end: int,
    fuzzy: bool,
) -> SpanValidation:
    """Confirm caller-supplied offsets actually contain ``span_text``."""
    in_bounds = 0 <= char_start <= char_end <= len(source_text)
    window = source_text[char_start:char_end] if in_bounds else None

    if window is not None:
        if window == span_text:
            return SpanValidation(STATUS_EXACT, span_text, char_start, char_end, window, False)
        if fuzzy and _normalize(window) == _normalize(span_text) and window:
            return SpanValidation(STATUS_NORMALIZED, span_text, char_start, char_end, window, True)

    # offsets disagree with span_text → flag mismatch (keep claimed offsets)
    return SpanValidation(STATUS_OFFSET_MISMATCH, span_text, char_start, char_end, window, False)


def _unpack(item: object) -> tuple[str, int | None, int | None]:
    """Coerce one ``spans`` entry into ``(span_text, char_start, char_end)``.

    Accepts a bare ``str``, a mapping with ``text``/``span_text`` (+ optional
    ``char_start``/``char_end``), a ``(text, start, end)`` tuple, or any object
    exposing those attributes.
    """
    if isinstance(item, str):
        return item, None, None
    if isinstance(item, dict):
        text = item.get("text", item.get("span_text", ""))
        return str(text), item.get("char_start"), item.get("char_end")
    if isinstance(item, (tuple, list)):
        if len(item) >= 3:
            return str(item[0]), item[1], item[2]
        if item:
            return str(item[0]), None, None
        return "", None, None
    text = getattr(item, "span_text", getattr(item, "text", ""))
    return str(text), getattr(item, "char_start", None), getattr(item, "char_end", None)


def validate_extraction(
    source_text: str,
    spans: object,
    *,
    fuzzy: bool = True,
) -> ExtractionReport:
    """Validate many spans and aggregate a status-count report (§6.10).

    ``spans`` is any iterable of entries accepted by :func:`_unpack`. The report
    tallies each status so a caller can enforce «no span → no fact» in bulk.
    """
    results: list[SpanValidation] = []
    counts = {
        STATUS_EXACT: 0,
        STATUS_NORMALIZED: 0,
        STATUS_NOT_FOUND: 0,
        STATUS_OFFSET_MISMATCH: 0,
    }
    for item in spans:  # type: ignore[attr-defined]
        text, start, end = _unpack(item)
        result = validate_span(source_text, text, char_start=start, char_end=end, fuzzy=fuzzy)
        results.append(result)
        counts[result.status] += 1

    return ExtractionReport(
        total=len(results),
        exact=counts[STATUS_EXACT],
        normalized=counts[STATUS_NORMALIZED],
        not_found=counts[STATUS_NOT_FOUND],
        offset_mismatch=counts[STATUS_OFFSET_MISMATCH],
        results=tuple(results),
    )
