"""§11.4/§11.7 — community-report findings normalization & cross-report ranking.

GraphRAG community reports carry a list of *findings* — short claims that
summarize what a community is about (§11.4). Их формат неоднороден: одни отчёты
дают findings как простые строки, другие — как ``{summary, explanation}`` пары.
This module normalizes both shapes into a frozen :class:`Finding` and ranks
findings *across* reports (§11.7) so a global answer can cite the strongest few.

Каждый :class:`Finding` inherits its parent report's ``rank`` and ``level`` plus
its own 0-based ``order`` within the report. :func:`top_findings` sorts the pooled
findings by ``(rank desc, level desc, order asc)``, dedupes by lowercased summary
(keeping the first / highest-ranked occurrence), and caps the result at ``k``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Finding:
    """One normalized community-report finding (§11.4).

    ``community_id`` / ``level`` / ``rank`` copy the parent report; ``order`` is the
    finding's 0-based index within that report's ``findings`` list.
    """

    community_id: int
    level: int
    order: int
    summary: str
    explanation: str
    rank: float

    def as_dict(self) -> dict[str, Any]:
        """Return the six fields as a plain dict (stable key set for serialization)."""
        return {
            "community_id": self.community_id,
            "level": self.level,
            "order": self.order,
            "summary": self.summary,
            "explanation": self.explanation,
            "rank": self.rank,
        }


def normalize_findings(report: dict) -> list[Finding]:
    """Normalize one community ``report`` into a list of :class:`Finding` (§11.4).

    ``report`` carries ``{community_id, level, rank, findings}``. Each entry in
    ``findings`` is either a plain ``str`` (mapped to ``summary`` with an empty
    ``explanation``) or a ``{summary, explanation}`` dict. ``order`` is the entry's
    0-based position. An empty ``findings`` list yields ``[]``.
    """
    community_id = int(report.get("community_id", 0))
    level = int(report.get("level", 0))
    rank = float(report.get("rank", 0.0))
    findings = report.get("findings") or []

    out: list[Finding] = []
    for order, raw in enumerate(findings):
        if isinstance(raw, str):
            summary, explanation = raw, ""
        else:
            summary = str(raw.get("summary", ""))
            explanation = str(raw.get("explanation", ""))
        out.append(
            Finding(
                community_id=community_id,
                level=level,
                order=order,
                summary=summary,
                explanation=explanation,
                rank=rank,
            )
        )
    return out


def top_findings(reports: list[dict], *, k: int) -> list[Finding]:
    """Pool, rank, dedupe and cap findings across ``reports`` (§11.7).

    Normalizes every report, sorts the pool by ``(rank desc, level desc, order asc)``,
    drops duplicate summaries (case-insensitive, keeping the first occurrence) and
    returns at most ``k`` findings.
    """
    pool: list[Finding] = []
    for report in reports:
        pool.extend(normalize_findings(report))

    pool.sort(key=lambda f: (-f.rank, -f.level, f.order))

    seen: set[str] = set()
    ranked: list[Finding] = []
    for finding in pool:
        key = finding.summary.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(finding)
        if len(ranked) >= k:
            break
    return ranked
