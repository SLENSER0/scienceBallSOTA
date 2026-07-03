"""Technical-assignment (техническое задание) report template (§24.16).

Шаблон отчёта для технического задания (ТЗ) — a *decision* dossier distinct from the
two neighbouring layouts: :mod:`report_sections` is the literature-review section layout
(Краткий вывод / Методы / Доказательная база / …) and :mod:`report_builder` is a
solution × metric comparison table. Neither is this ТЗ template.

The ТЗ template fixes six ordered sections (§24.16):

1. Проблема               — the problem statement (problem);
2. Входные условия         — the input conditions / constraints (input_conditions);
3. Сравниваемые технологии — the technologies under comparison (compared_technologies);
4. Рекомендация            — the recommendation / выбор (recommendation);
5. Риски                   — the risks of the recommendation (risks);
6. Доказательная база       — the backing Evidence ids (evidence_ids).

A well-formed ТЗ names a problem, lists the technologies it weighs, and makes an
evidence-backed recommendation. :func:`validate_spec_report` reports the ways a draft
falls short as machine-readable issue codes (``missing_problem``, ``no_recommendation``,
``recommendation_without_evidence``, ``no_compared_technologies``).

Pure Python and deterministic: no graph store, no LLM. The result is a frozen dataclass
exposing ``as_dict()`` / ``from_dict()`` for JSON transport, plus a ``to_markdown``
renderer producing the six RU sections in canonical order.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Issue codes returned by validate_spec_report (§24.16).
ISSUE_MISSING_PROBLEM = "missing_problem"
ISSUE_NO_RECOMMENDATION = "no_recommendation"
ISSUE_RECOMMENDATION_WITHOUT_EVIDENCE = "recommendation_without_evidence"
ISSUE_NO_COMPARED_TECHNOLOGIES = "no_compared_technologies"

# The canonical ordered ТЗ section schema (§24.16): (machine field, RU heading). The
# order here *is* the report order and is never reshuffled.
SECTION_SPECS: tuple[tuple[str, str], ...] = (
    ("problem", "Проблема"),
    ("input_conditions", "Входные условия"),
    ("compared_technologies", "Сравниваемые технологии"),
    ("recommendation", "Рекомендация"),
    ("risks", "Риски"),
    ("evidence_ids", "Доказательная база"),
)

# Dash rendered in place of an empty section body in the markdown output (тире).
EMPTY_DASH = "—"


def section_titles() -> list[str]:
    """Return the canonical RU ТЗ section titles in report order (§24.16)."""
    return [title for _field, title in SECTION_SPECS]


def _dedup(items: Iterable[Any]) -> tuple[str, ...]:
    """Normalise into stripped, deduped strings preserving first-seen order (§24.16)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


@dataclass(frozen=True)
class SpecReport:
    """A technical-assignment (ТЗ) report in canonical RU order (§24.16).

    Attributes:
        problem: the problem statement (проблема).
        input_conditions: the input conditions / constraints (входные условия).
        compared_technologies: the technologies under comparison (сравниваемые).
        recommendation: the recommended choice (рекомендация); ``""`` when undecided.
        risks: the risks of the recommendation (риски).
        evidence_ids: the backing Evidence ids (доказательная база).

    The tuple fields are already deduplicated with first-seen order preserved.
    """

    problem: str = ""
    input_conditions: tuple[str, ...] = ()
    compared_technologies: tuple[str, ...] = ()
    recommendation: str = ""
    risks: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Serialise the whole report to a JSON-ready dict (§24.16)."""
        return {
            "problem": self.problem,
            "input_conditions": list(self.input_conditions),
            "compared_technologies": list(self.compared_technologies),
            "recommendation": self.recommendation,
            "risks": list(self.risks),
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpecReport:
        """Rebuild a report from :meth:`as_dict` output (round-trip stable)."""
        return cls(
            problem=str(data.get("problem", "")),
            input_conditions=_dedup(data.get("input_conditions", ())),
            compared_technologies=_dedup(data.get("compared_technologies", ())),
            recommendation=str(data.get("recommendation", "")),
            risks=_dedup(data.get("risks", ())),
            evidence_ids=_dedup(data.get("evidence_ids", ())),
        )

    def to_markdown(self) -> str:
        """Render the six ТЗ sections as ``## heading`` blocks in order (§24.16).

        ``problem`` and ``recommendation`` render their prose directly under the
        heading; the tuple fields render each item as a ``- item`` bullet. An empty
        section body renders as a single ``—`` dash so every heading has content.
        """
        prose = {"problem": self.problem, "recommendation": self.recommendation}
        blocks: list[str] = []
        for field_name, title in SECTION_SPECS:
            lines = [f"## {title}"]
            if field_name in prose:
                text = prose[field_name].strip()
                lines.append(text if text else EMPTY_DASH)
            else:
                items = getattr(self, field_name)
                if items:
                    lines.extend(f"- {item}" for item in items)
                else:
                    lines.append(EMPTY_DASH)
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n"


def build_spec_report(
    *,
    problem: str = "",
    input_conditions: Iterable[Any] = (),
    compared_technologies: Iterable[Any] = (),
    recommendation: str = "",
    risks: Iterable[Any] = (),
    evidence_ids: Iterable[Any] = (),
) -> SpecReport:
    """Build a :class:`SpecReport` from raw ТЗ fields (§24.16).

    Prose fields are stripped; the tuple fields are deduplicated with first-seen order
    preserved (§24.16). The result is a frozen, canonical-order ТЗ report.
    """
    return SpecReport(
        problem=str(problem).strip(),
        input_conditions=_dedup(input_conditions),
        compared_technologies=_dedup(compared_technologies),
        recommendation=str(recommendation).strip(),
        risks=_dedup(risks),
        evidence_ids=_dedup(evidence_ids),
    )


def validate_spec_report(report: SpecReport) -> tuple[str, ...]:
    """Return the ТЗ well-formedness issue codes for ``report`` (§24.16).

    Codes (in deterministic order):

    - ``missing_problem`` — the problem statement is empty/blank;
    - ``no_compared_technologies`` — no technologies are being compared;
    - ``no_recommendation`` — no recommendation was made;
    - ``recommendation_without_evidence`` — a recommendation with no backing Evidence.

    A fully-populated report yields an empty tuple.
    """
    issues: list[str] = []
    if not report.problem.strip():
        issues.append(ISSUE_MISSING_PROBLEM)
    if not report.compared_technologies:
        issues.append(ISSUE_NO_COMPARED_TECHNOLOGIES)
    if not report.recommendation.strip():
        issues.append(ISSUE_NO_RECOMMENDATION)
    elif not report.evidence_ids:
        issues.append(ISSUE_RECOMMENDATION_WITHOUT_EVIDENCE)
    return tuple(issues)
