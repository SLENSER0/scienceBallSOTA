"""Structured report-section assembly (§24.17).

Сборка итогового ответа по фиксированным разделам. Given the already-resolved bodies
of the answer — summary, methods, evidence, gaps, contradictions, recommendations and
pilot checks — this module lays them out in the *canonical* RU section order and drops
any section that has no content (пустой раздел не выводится).

The canonical order (§24.17) is fixed and never reshuffled:

1. Краткий вывод        — the headline conclusion (summary);
2. Методы и решения     — methods / candidate solutions (methods);
3. Доказательная база   — supporting evidence (evidence);
4. Пробелы              — coverage gaps / пробелы (gaps);
5. Противоречия         — contradictions between sources (contradictions);
6. Рекомендации         — recommendations, optional (recommendations);
7. Что проверить пилотно — what to validate in a pilot, optional (pilot checks).

A section body may be a single prose string (параграф) or a sequence of bullet items
(список); each item is stripped and blank items are dropped. A section whose body is
``None``, an empty/blank string, or an all-blank sequence is skipped entirely — the
resulting report only carries the sections that actually have content.

Pure Python and deterministic: no graph store, no LLM. Results are frozen dataclasses
exposing ``as_dict()`` / ``from_dict()`` for JSON transport, plus a ``to_markdown``
renderer producing the RU sections as ``## heading`` blocks in canonical order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# A section body: prose string, a sequence of bullet items, or nothing at all (§24.17).
SectionBody = str | Sequence[str] | None

# Section kinds: a single prose paragraph vs. a bulleted list (маркированный список).
KIND_PROSE = "prose"
KIND_LIST = "list"

# The canonical ordered section schema (§24.17): (machine key, RU heading). The order
# here *is* the report order and is never reshuffled.
SECTION_SPECS: tuple[tuple[str, str], ...] = (
    ("summary", "Краткий вывод"),
    ("methods", "Методы и решения"),
    ("evidence", "Доказательная база"),
    ("gaps", "Пробелы"),
    ("contradictions", "Противоречия"),
    ("recommendations", "Рекомендации"),
    ("pilot", "Что проверить пилотно"),
)


def section_titles() -> list[str]:
    """Return the canonical RU section titles in report order (§24.17).

    This is the fixed schema — the full seven-title order — independent of whether any
    particular report actually populates a given section.
    """
    return [title for _key, title in SECTION_SPECS]


@dataclass(frozen=True)
class Section:
    """One rendered report section — a titled prose or bulleted body (§24.17).

    ``key`` is the stable machine name (e.g. ``summary``), ``title`` the RU heading,
    ``kind`` one of :data:`KIND_PROSE` / :data:`KIND_LIST`, and ``body`` the normalized,
    non-empty lines (a single element for prose, one per bullet for a list).
    """

    key: str
    title: str
    kind: str
    body: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{key, title, kind, body}`` (JSON-ready)."""
        return {
            "key": self.key,
            "title": self.title,
            "kind": self.kind,
            "body": list(self.body),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Section:
        """Rebuild a section from its serialised form (inverse of :meth:`as_dict`)."""
        return cls(
            key=str(data["key"]),
            title=str(data["title"]),
            kind=str(data.get("kind", KIND_LIST)),
            body=tuple(str(item) for item in data.get("body", ())),
        )


@dataclass(frozen=True)
class Report:
    """A structured multi-section report in canonical RU order (§24.17).

    Carries only the sections that had content — empty sections are never stored, so
    ``sections`` is already the exact, ordered list of what will be rendered.
    """

    sections: tuple[Section, ...] = ()

    def titles(self) -> list[str]:
        """Return the RU titles of the *present* sections, in report order."""
        return [section.title for section in self.sections]

    def as_dict(self) -> dict[str, Any]:
        """Serialise the whole report to a JSON-ready dict (§24.17)."""
        return {"sections": [section.as_dict() for section in self.sections]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Report:
        """Rebuild a report from :meth:`as_dict` output (round-trip stable)."""
        return cls(sections=tuple(Section.from_dict(s) for s in data.get("sections", ())))

    def to_markdown(self) -> str:
        """Render the report as ``## heading`` blocks in canonical order (§24.17).

        Prose sections render the paragraph directly under the heading; list sections
        render each item as a ``- item`` bullet. Blocks are separated by a blank line
        and the whole document ends with a trailing newline. An empty report (no
        sections) renders as the empty string.
        """
        blocks: list[str] = []
        for section in self.sections:
            lines = [f"## {section.title}"]
            if section.kind == KIND_LIST:
                lines.extend(f"- {item}" for item in section.body)
            else:
                lines.extend(section.body)
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n" if blocks else ""


def _normalize(body: SectionBody) -> tuple[str, tuple[str, ...]] | None:
    """Normalise a raw section body into ``(kind, lines)`` or ``None`` when empty.

    A string collapses to a single prose line (skipped if blank); a sequence collapses
    to a bulleted list of its stripped, non-blank items (skipped if none remain).
    """
    if body is None:
        return None
    if isinstance(body, str):
        text = body.strip()
        return (KIND_PROSE, (text,)) if text else None
    items = tuple(str(item).strip() for item in body if str(item).strip())
    return (KIND_LIST, items) if items else None


def assemble_sections(
    *,
    summary: SectionBody,
    methods: SectionBody,
    evidence: SectionBody,
    gaps: SectionBody,
    contradictions: SectionBody,
    recommendations: SectionBody = None,
    pilot_checks: SectionBody = None,
) -> Report:
    """Assemble answer bodies into a canonical-order :class:`Report` (§24.17).

    Each argument is a section body — a prose string or a sequence of bullet items.
    Sections are emitted strictly in the :data:`SECTION_SPECS` order (Краткий вывод →
    Методы и решения → Доказательная база → Пробелы → Противоречия → Рекомендации →
    Что проверить пилотно). Any section whose body is ``None``, blank, or an all-blank
    sequence is skipped (пустой раздел не выводится). ``recommendations`` and
    ``pilot_checks`` are optional (default ``None``) and simply absent when not given.
    """
    raw: dict[str, SectionBody] = {
        "summary": summary,
        "methods": methods,
        "evidence": evidence,
        "gaps": gaps,
        "contradictions": contradictions,
        "recommendations": recommendations,
        "pilot": pilot_checks,
    }
    sections: list[Section] = []
    for key, title in SECTION_SPECS:
        normalized = _normalize(raw[key])
        if normalized is None:
            continue
        kind, lines = normalized
        sections.append(Section(key=key, title=title, kind=kind, body=lines))
    return Report(sections=tuple(sections))
