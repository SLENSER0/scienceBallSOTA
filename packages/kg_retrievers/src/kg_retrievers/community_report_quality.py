"""Community-report quality scoring (§11.18).

Grades a GraphRAG-style *community report* dict on completeness, findings count,
summary length and source presence, blending these into a ``score`` in ``[0, 1]``
and attaching human-readable ``flags`` for the weak spots.

Оценка качества отчёта по сообществу: полнота обязательных полей, число выводов,
длина резюме и наличие источников сводятся в балл ``0..1`` с пометками проблем.

Pure, read-only data logic — no store access. Required fields are
``title, summary, findings, rank, doc_ids``; ``completeness`` is the fraction of
those that are present *and* non-empty.
"""

from __future__ import annotations

from dataclasses import dataclass

# Required report fields whose presence-and-non-emptiness drives completeness.
_REQUIRED: tuple[str, ...] = ("title", "summary", "findings", "rank", "doc_ids")

# Score = weighted blend of completeness, findings signal and source presence.
_W_COMPLETE: float = 0.6
_W_FINDINGS: float = 0.25
_W_SOURCES: float = 0.15
# Findings signal saturates at this many findings (maps count → 0..1).
_FINDINGS_SAT: int = 3


def _is_nonempty(value: object) -> bool:
    """True when ``value`` is present and not an empty string/collection.

    Booleans and non-zero numbers count as present; ``0``/``0.0`` also count
    (a ``rank`` of ``0`` is a real value), but ``None`` and empty ``str``/list/
    dict/tuple do not.
    """
    if value is None:
        return False
    if isinstance(value, (str, list, tuple, dict, set)):
        return len(value) > 0
    return True


@dataclass(frozen=True)
class ReportQuality:
    """Quality verdict for a single community report (§11.18).

    - ``community_id`` — id of the scored community (``-1`` when absent);
    - ``completeness`` — fraction of required fields present and non-empty;
    - ``n_findings`` — number of findings in the report;
    - ``summary_len`` — character length of the (stripped) summary;
    - ``has_sources`` — whether ``doc_ids`` is non-empty;
    - ``score`` — weighted blend in ``[0, 1]``;
    - ``flags`` — sorted issue tags, e.g. ``short_summary``/``no_findings``/
      ``no_sources``.
    """

    community_id: int
    completeness: float
    n_findings: int
    summary_len: int
    has_sources: bool
    score: float
    flags: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "community_id": self.community_id,
            "completeness": self.completeness,
            "n_findings": self.n_findings,
            "summary_len": self.summary_len,
            "has_sources": self.has_sources,
            "score": self.score,
            "flags": list(self.flags),
        }


def score_report(report: dict, *, min_summary: int = 40) -> ReportQuality:
    """Score one ``report`` dict into a :class:`ReportQuality` (§11.18).

    ``completeness`` is the fraction of ``_REQUIRED`` fields that are present and
    non-empty. ``score`` blends completeness, a findings signal (saturating at
    ``_FINDINGS_SAT``) and source presence. Flags:

    - ``short_summary`` when the stripped summary is shorter than ``min_summary``;
    - ``no_findings`` when there are zero findings;
    - ``no_sources`` when ``doc_ids`` is empty.
    """
    present = sum(1 for f in _REQUIRED if _is_nonempty(report.get(f)))
    completeness = present / len(_REQUIRED)

    findings = report.get("findings") or []
    n_findings = len(findings) if isinstance(findings, (list, tuple)) else 0

    summary = report.get("summary")
    summary_len = len(summary.strip()) if isinstance(summary, str) else 0

    doc_ids = report.get("doc_ids") or []
    has_sources = _is_nonempty(doc_ids)

    findings_signal = min(n_findings, _FINDINGS_SAT) / _FINDINGS_SAT
    score = (
        _W_COMPLETE * completeness
        + _W_FINDINGS * findings_signal
        + _W_SOURCES * (1.0 if has_sources else 0.0)
    )
    score = max(0.0, min(1.0, score))

    flags: list[str] = []
    if summary_len < min_summary:
        flags.append("short_summary")
    if n_findings == 0:
        flags.append("no_findings")
    if not has_sources:
        flags.append("no_sources")

    community_id = report.get("community_id")
    cid = int(community_id) if isinstance(community_id, int) else -1

    return ReportQuality(
        community_id=cid,
        completeness=completeness,
        n_findings=n_findings,
        summary_len=summary_len,
        has_sources=has_sources,
        score=score,
        flags=tuple(sorted(flags)),
    )


def rank_by_quality(reports: list[dict]) -> list[ReportQuality]:
    """Score every report and return them sorted by ``score`` descending.

    Ties keep a stable order by ``community_id`` so the ranking is deterministic.
    """
    scored = [score_report(r) for r in reports]
    return sorted(scored, key=lambda q: (-q.score, q.community_id))
