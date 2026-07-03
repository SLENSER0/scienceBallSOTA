"""Coverage burndown projection over an ordered series of snapshots (§25.5).

Projects a *closure ETA* (расчётный срок закрытия) over an ordered series of
coverage snapshots taken during the ingestion pipeline. Each snapshot exposes an
``open_cells`` count — the number of still-open coverage cells / gaps at that
run. Given a chronological list, :func:`coverage_burndown` computes an average
close-rate and the number of remaining runs needed to reach zero open cells.

Burndown-проекция покрытия: средняя скорость закрытия и прогноз оставшихся
прогонов до полного закрытия.

This is deliberately distinct from two sibling utilities:

- ``coverage_delta.py`` compares *two* material snapshots (covered flags);
- ``gap_trends.py`` diffs gap-id *sets* between snapshots.

Here we operate on scalar open-cell counts and produce a linear projection. The
result is a frozen dataclass exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BurndownReport:
    """Linear burndown projection over coverage snapshots (§25.5).

    - ``points`` — per-snapshot echo, each a ``{"open": <int>}`` mapping in the
      original order (порядок прогонов сохранён);
    - ``total_closed`` — ``first_open - last_open`` (signed; negative when the
      open count grew over the series);
    - ``avg_close_rate`` — ``total_closed / (len - 1)`` cells closed per run,
      ``0.0`` when fewer than two snapshots are supplied;
    - ``remaining`` — the last snapshot's open-cell count;
    - ``eta_runs`` — ``remaining / avg_close_rate`` when the rate is strictly
      positive, else ``None`` (no finite ETA when nothing is closing).
    """

    points: tuple[dict, ...]
    total_closed: int
    avg_close_rate: float
    remaining: int
    eta_runs: float | None

    def as_dict(self) -> dict:
        return {
            "points": [dict(point) for point in self.points],
            "total_closed": self.total_closed,
            "avg_close_rate": self.avg_close_rate,
            "remaining": self.remaining,
            "eta_runs": self.eta_runs,
        }


def coverage_burndown(snapshots: list[dict], *, open_key: str = "open_cells") -> BurndownReport:
    """Project a closure ETA over ordered coverage snapshots (§25.5).

    ``snapshots`` is a chronological list; each item exposes ``open_key`` (an
    open-cell count). Returns a :class:`BurndownReport`. With zero or one
    snapshot the close-rate is ``0.0`` and ``eta_runs`` is ``None``. A flat or
    increasing series likewise yields no finite ETA.

    Прогноз срока закрытия по упорядоченным снимкам покрытия.
    """
    opens = [int(snapshot[open_key]) for snapshot in snapshots]
    points = tuple({"open": value} for value in opens)

    if len(opens) < 2:
        remaining = opens[-1] if opens else 0
        return BurndownReport(
            points=points,
            total_closed=0,
            avg_close_rate=0.0,
            remaining=remaining,
            eta_runs=None,
        )

    first_open, last_open = opens[0], opens[-1]
    total_closed = first_open - last_open
    avg_close_rate = total_closed / (len(opens) - 1)
    remaining = last_open
    eta_runs = remaining / avg_close_rate if avg_close_rate > 0 else None

    return BurndownReport(
        points=points,
        total_closed=total_closed,
        avg_close_rate=avg_close_rate,
        remaining=remaining,
        eta_runs=eta_runs,
    )
