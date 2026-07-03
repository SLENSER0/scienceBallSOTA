"""Per-report freshness / staleness vs source-doc updates (§11.10).

A community report is a cached summary built at some ``built_at`` timestamp over a
set of source ``doc_ids``. When any of those source documents is updated *after*
the report was built, the report becomes **stale** and should be rebuilt. This
module provides a pure, read-only assessment of that condition.

Проверяет актуальность отчёта сообщества: если любой исходный документ обновлён
после сборки отчёта, отчёт считается устаревшим (stale) и требует пересборки.

Freshness rules:
- ``newest_source_ts`` — max ``doc_updated_at[d]`` over the report's ``doc_ids``
  that are present in the map (``0.0`` if none present);
- ``stale`` — ``True`` iff ``newest_source_ts > built_at`` (strict);
- ``lag_seconds`` — ``max(0.0, newest_source_ts - built_at)``.

Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Freshness:
    """Freshness verdict for one community report (§11.10).

    - ``community_id`` — id of the assessed community;
    - ``stale`` — ``True`` iff a source doc is newer than the report;
    - ``newest_source_ts`` — newest known source-doc update timestamp;
    - ``report_ts`` — the report's ``built_at`` timestamp;
    - ``lag_seconds`` — non-negative staleness lag in seconds.
    """

    community_id: int
    stale: bool
    newest_source_ts: float
    report_ts: float
    lag_seconds: float

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping of this verdict."""
        return {
            "community_id": self.community_id,
            "stale": self.stale,
            "newest_source_ts": self.newest_source_ts,
            "report_ts": self.report_ts,
            "lag_seconds": self.lag_seconds,
        }


def assess_freshness(report: dict, doc_updated_at: dict[str, float]) -> Freshness:
    """Assess whether ``report`` is stale vs the latest source-doc updates.

    ``report`` must expose ``{community_id, built_at, doc_ids}``. Only ``doc_ids``
    present in ``doc_updated_at`` contribute to ``newest_source_ts``; absent ids
    are ignored. Оценивает устаревание отчёта относительно обновлений источников.
    """
    community_id = int(report["community_id"])
    report_ts = float(report["built_at"])
    doc_ids = report.get("doc_ids") or []
    known = [float(doc_updated_at[d]) for d in doc_ids if d in doc_updated_at]
    newest_source_ts = max(known) if known else 0.0
    stale = newest_source_ts > report_ts
    lag_seconds = max(0.0, newest_source_ts - report_ts)
    return Freshness(
        community_id=community_id,
        stale=stale,
        newest_source_ts=newest_source_ts,
        report_ts=report_ts,
        lag_seconds=lag_seconds,
    )


def stale_reports(reports: list[dict], doc_updated_at: dict[str, float]) -> list[int]:
    """Return sorted ``community_id``s of reports that are stale (§11.10).

    Возвращает отсортированные идентификаторы устаревших отчётов сообществ.
    """
    ids = [
        assess_freshness(r, doc_updated_at).community_id
        for r in reports
        if assess_freshness(r, doc_updated_at).stale
    ]
    return sorted(ids)
