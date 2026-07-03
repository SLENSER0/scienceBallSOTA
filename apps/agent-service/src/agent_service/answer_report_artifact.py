"""§13.17 экспортируемый report-артефакт / self-contained markdown export artifact.

The §5.2.2 answer view carries an "export report" button: the user downloads the
whole answer as one self-contained markdown file. :mod:`answer_assembler` and
:mod:`answer_tabs` build the on-screen tab payloads, but neither renders that
downloadable document — this module does.

:func:`build_report` folds an ``AnswerPayload``-like dict
(``{'summary','experiments','evidence','gaps','contradictions','citations'}``) into a
:class:`ReportArtifact` whose ``markdown`` is a fixed-order document. Sections appear
in the canonical order ``## Summary``, ``## Experiments``, ``## Gaps``,
``## Contradictions``, ``## Citations``; a section whose input is empty is omitted
entirely, and ``sections`` lists exactly the emitted titles (без префикса ``## ``) in
that same order. Pure-python and deterministic — no graph store, no LLM.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# The eight experiment columns rendered as a markdown pipe table (§5.2.2).
_EXPERIMENT_COLUMNS: tuple[str, ...] = (
    "material",
    "processing",
    "property",
    "value",
    "unit",
    "effect",
    "confidence",
    "evidence_ids",
)


@dataclass(frozen=True)
class ReportArtifact:
    """A rendered, downloadable answer report (§5.2.2 export button).

    ``markdown`` is the full self-contained document; ``sections`` lists the titles
    of the sections actually emitted (``'Summary'``, ``'Experiments'``, …) in document
    order, so a caller can build a table of contents without re-parsing the text.
    """

    markdown: str
    sections: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict ``{'markdown', 'sections': [...]}``."""
        return {"markdown": self.markdown, "sections": list(self.sections)}


def _cell(value: Any) -> str:
    """Render one experiment cell (список evidence_ids → 'a,b', иначе str())."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def _experiments_block(experiments: Sequence[Any]) -> str:
    """Render the experiments pipe table: header + separator + one row per experiment."""
    header = "| " + " | ".join(_EXPERIMENT_COLUMNS) + " |"
    separator = "| " + " | ".join("---" for _ in _EXPERIMENT_COLUMNS) + " |"
    rows: list[str] = []
    for exp in experiments:
        mapping: Mapping[str, Any] = exp if isinstance(exp, Mapping) else {}
        cells = [_cell(mapping.get(col)) for col in _EXPERIMENT_COLUMNS]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator, *rows])


def _bullet_block(items: Sequence[Any]) -> str:
    """Render a plain bullet list, one ``- <item>`` line per entry."""
    return "\n".join(f"- {item}" for item in items)


def _citations_block(citations: Sequence[Any]) -> str:
    """Render each evidence id as ``- ev:<id>`` (§5.2.2 citations list)."""
    return "\n".join(f"- ev:{cid}" for cid in citations)


def build_report(answer: dict) -> ReportArtifact:
    """Render an ``AnswerPayload``-like dict into a :class:`ReportArtifact` (§13.17).

    ``answer`` is read for ``summary`` (str), ``experiments`` (sequence of dicts),
    ``gaps`` / ``contradictions`` (sequences) and ``citations`` (sequence of evidence
    ids). Sections are emitted in the fixed order Summary → Experiments → Gaps →
    Contradictions → Citations; each section whose input is falsy (пустая строка /
    пустой список / отсутствует) is skipped, and its title never appears in
    ``sections``. The ``evidence`` key is carried by the DTO but has no section of its
    own (evidence ids surface per-experiment and in Citations).
    """
    summary = answer.get("summary") or ""
    experiments = answer.get("experiments") or []
    gaps = answer.get("gaps") or []
    contradictions = answer.get("contradictions") or []
    citations = answer.get("citations") or []

    parts: list[tuple[str, str]] = []
    if summary:
        parts.append(("Summary", str(summary)))
    if experiments:
        parts.append(("Experiments", _experiments_block(experiments)))
    if gaps:
        parts.append(("Gaps", _bullet_block(gaps)))
    if contradictions:
        parts.append(("Contradictions", _bullet_block(contradictions)))
    if citations:
        parts.append(("Citations", _citations_block(citations)))

    blocks = [f"## {title}\n\n{body}" for title, body in parts]
    markdown = "\n\n".join(blocks)
    sections = tuple(title for title, _ in parts)
    return ReportArtifact(markdown=markdown, sections=sections)
