"""Findings-to-member mention coverage (§11.4).

Auditability metric: what fraction of a community's *member entities* are actually
named somewhere across its report findings text. Members that a summary silently
omits are flagged in ``uncovered_members`` so a reviewer can spot the blind spots.

Аудит покрытия: какая доля сущностей-участников сообщества реально упомянута в
тексте выводов отчёта; молча пропущенные участники помечаются отдельно.

Distinct from ``community_findings.py`` (which normalizes/ranks findings) and from
``community_report_quality.py`` (which grades field completeness and never checks
member mentions). Pure, read-only string logic — no store access.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class FindingsCoverage:
    """Coverage verdict of member entities over findings text (§11.4).

    - ``n_members`` — number of distinct member names checked;
    - ``n_covered`` — how many members are named in the findings text;
    - ``coverage`` — ``n_covered / n_members`` (``0.0`` when there are no members);
    - ``uncovered_members`` — members not found, in original order.
    """

    n_members: int
    n_covered: int
    coverage: float
    uncovered_members: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "n_members": self.n_members,
            "n_covered": self.n_covered,
            "coverage": self.coverage,
            "uncovered_members": list(self.uncovered_members),
        }


def findings_member_coverage(member_names: Iterable[str], findings_text: str) -> FindingsCoverage:
    """Compute member-mention coverage over ``findings_text`` (§11.4).

    Matching is case-insensitive substring matching over the concatenated findings
    text: a member counts as covered when its (stripped) name appears anywhere in
    the lowercased text. Empty/whitespace-only member names never match. Coverage is
    ``n_covered / n_members``, or ``0.0`` when there are no members.

    Сопоставление — без учёта регистра, по вхождению подстроки в текст выводов.
    """
    members = list(member_names)
    n_members = len(members)
    haystack = findings_text.lower()

    uncovered: list[str] = []
    n_covered = 0
    for name in members:
        needle = name.strip().lower()
        if needle and needle in haystack:
            n_covered += 1
        else:
            uncovered.append(name)

    coverage = n_covered / n_members if n_members else 0.0
    return FindingsCoverage(
        n_members=n_members,
        n_covered=n_covered,
        coverage=coverage,
        uncovered_members=tuple(uncovered),
    )
