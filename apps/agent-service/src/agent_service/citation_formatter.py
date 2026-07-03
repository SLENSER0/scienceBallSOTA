"""§13.15 форматирование цитат для ответов / citation formatting for answers.

Pure-python, deterministic projection over EvidenceRef-shaped span pointers
(see :mod:`agent_service.evidence_assembler` and ``kg_common.EvidenceRef`` for the
shape — evidence_id / doc_id / page / text). Nothing here touches the graph store,
so the whole module stays unit-testable without a seeded Kuzu database.

Three helpers:

* :func:`number_citations` — assign stable ``[n]`` numbers to spans, deduplicated
  by ``evidence_id`` (один довод — один номер / one evidence — one number).
* :func:`format_reference_list` — render a numbered RU/EN reference block
  ``[n] doc … с. page``.
* :func:`inject_markers` — no-op passthrough that validates every inline ``[n]``
  used in a text has a matching citation (raise on dangling / висячая ссылка).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

# Max snippet length (символов / chars) before an ellipsis truncation.
_SNIPPET_MAX = 160
_ELLIPSIS = "…"

# Inline citation marker, e.g. ``[1]`` / ``[12]`` — one or more digits in brackets.
_MARKER_RE = re.compile(r"\[(\d+)\]")

# Russian page abbreviation ("страница" → "с.", кириллица) for the reference block.
_PAGE_ABBR = "с."

# Placeholder when a span carries no document id (документ неизвестен / unknown doc).
_NO_DOCUMENT = "(без документа / no document)"


class _EvidenceLike(Protocol):
    """Duck-typed EvidenceRef shape (§7.3) — see evidence_assembler for the model."""

    evidence_id: str
    doc_id: str | None
    page: int | None
    text: str | None


@dataclass(frozen=True)
class Citation:
    """One numbered citation for an answer (§13.15).

    ``n`` is the stable 1-based number rendered inline as ``[n]``; the remaining
    fields point at the source span — ``doc_id`` (документ-источник), ``page``
    (страница) and a truncated ``snippet`` (фрагмент) for display.
    """

    n: int
    evidence_id: str
    doc_id: str | None
    page: int | None
    snippet: str | None

    @property
    def marker(self) -> str:
        """Inline marker ``[n]`` for this citation."""
        return f"[{self.n}]"

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{n, evidence_id, doc_id, page, snippet}``."""
        return {
            "n": self.n,
            "evidence_id": self.evidence_id,
            "doc_id": self.doc_id,
            "page": self.page,
            "snippet": self.snippet,
        }


def _truncate(text: str | None, limit: int = _SNIPPET_MAX) -> str | None:
    """Trim ``text`` to ``limit`` chars, appending an ellipsis when it is cut."""
    if text is None:
        return None
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + _ELLIPSIS


def number_citations(evidence_refs: Iterable[_EvidenceLike]) -> list[Citation]:
    """Assign stable ``[n]`` numbers to EvidenceRef spans, deduped by ``evidence_id``.

    The first occurrence of each ``evidence_id`` (in input order) claims the next
    number starting at ``1``; later repeats of the same ``evidence_id`` are skipped
    without leaving a gap in the numbering (стабильный порядок / stable order).
    Returns the numbered :class:`Citation` list; an empty input yields ``[]``.
    """
    citations: list[Citation] = []
    seen: set[str] = set()
    for ref in evidence_refs:
        eid = str(ref.evidence_id)
        if eid in seen:
            continue  # same довод already numbered — one evidence, one number
        seen.add(eid)
        citations.append(
            Citation(
                n=len(citations) + 1,
                evidence_id=eid,
                doc_id=ref.doc_id,
                page=ref.page,
                snippet=_truncate(ref.text),
            )
        )
    return citations


def citation_map(citations: Iterable[Citation]) -> dict[int, Citation]:
    """Index citations by their number ``n`` (номер → цитата) for validation."""
    return {c.n: c for c in citations}


def format_reference_list(citations: Iterable[Citation]) -> str:
    """Render a numbered RU/EN reference block ``[n] doc … с. page`` (§13.15).

    Each citation becomes one line ``[n] <doc_id>, с. <page> — <snippet>``; missing
    parts degrade gracefully (нет документа → placeholder, нет страницы → без ``с.``,
    нет фрагмента → без тире). Empty input yields an empty string.
    """
    lines: list[str] = []
    for cit in citations:
        parts = [f"{cit.marker} {cit.doc_id or _NO_DOCUMENT}"]
        if cit.page is not None:
            parts.append(f"{_PAGE_ABBR} {cit.page}")
        line = ", ".join(parts)
        if cit.snippet:
            line = f"{line} — {cit.snippet}"
        lines.append(line)
    return "\n".join(lines)


def inject_markers(text: str, mapping: Mapping[int, Any]) -> str:
    """No-op passthrough validating every inline ``[n]`` in ``text`` is cited (§13.15).

    Scans ``text`` for inline ``[n]`` markers and checks each number ``n`` is a key of
    ``mapping`` (номер → цитата / number → citation, e.g. from :func:`citation_map`).
    Raises :class:`ValueError` on a dangling marker — ``[9]`` без цитаты / with no
    citation. On success returns ``text`` unchanged (маркеры уже в тексте).
    """
    valid = set(mapping)
    used = {int(m) for m in _MARKER_RE.findall(text)}
    dangling = sorted(used - valid)
    if dangling:
        markers = ", ".join(f"[{n}]" for n in dangling)
        raise ValueError(f"висячая ссылка / dangling citation marker(s): {markers}")
    return text
