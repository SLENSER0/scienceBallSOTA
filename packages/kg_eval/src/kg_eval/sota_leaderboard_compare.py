"""SOTA leaderboard compare: our metrics vs published external numbers (§23.31/§23.35).

Сравнение наших измеренных метрик с ОПУБЛИКОВАННЫМИ внешними числами SOTA
(LightRAG, olmOCR-Bench и т. п.). Это НЕ :mod:`baseline_benchmark`, который
сравнивает наши внутренние прогоны между собой: здесь второй участник —
внешняя опубликованная цифра из чужого лидерборда, а не наш базовый прогон.
Для каждой метрики считается ``delta`` (наша минус внешняя, либо внешняя минус
наша при «меньше — лучше»), нормализованная по знаку так, что положительное
значение всегда означает, что мы не хуже внешней системы. ``beats`` истинно
при ``delta >= 0`` (ничья засчитывается как «не проиграли»). Вердикт —
``"competitive"``, если мы обошли (или сравнялись) большинство метрик, иначе
``"behind"``.

Compares our measured metrics against published external SOTA numbers (LightRAG,
olmOCR-Bench, etc.). This is NOT :mod:`baseline_benchmark`, which compares our
own internal runs: here the second party is an external published leaderboard
figure, not one of our baseline runs. Per metric ``delta`` is sign-adjusted so a
positive value always means we are at least as good as the external system;
``beats`` is ``delta >= 0`` (a tie counts as not-behind). ``verdict`` is
``"competitive"`` iff we beat/tie a majority of metrics, else ``"behind"``.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Rounding applied to ``delta`` before its sign test — guards against float noise
# (e.g. ``0.9 - 0.82 == 0.07999999999999996``) near the zero boundary.
_DELTA_NDIGITS = 9

_COMPETITIVE = "competitive"
_BEHIND = "behind"


@dataclass(frozen=True)
class SotaRow:
    """One metric compared to an external SOTA number — дельта и исход (§23.31/§23.35).

    ``ours`` — наше измеренное значение, ``external`` — опубликованное значение
    системы ``external_system``. ``delta`` нормализована по знаку (плюс = мы не
    хуже), ``beats`` истинно при ``delta >= 0``.

    ``ours`` is our measured value, ``external`` the published value of
    ``external_system``. ``delta`` is sign-adjusted (positive means we are at
    least as good); ``beats`` is ``delta >= 0``.
    """

    metric: str
    ours: float
    external: float
    external_system: str
    delta: float
    beats: bool

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "metric": self.metric,
            "ours": self.ours,
            "external": self.external,
            "external_system": self.external_system,
            "delta": self.delta,
            "beats": self.beats,
        }


@dataclass(frozen=True)
class SotaComparison:
    """Verdict over all external-SOTA comparisons — сколько обошли и итог (§23.31/§23.35).

    ``rows`` отсортированы по имени метрики для детерминизма. ``n_beat`` — число
    метрик, где ``beats`` истинно (включая ничьи). ``verdict`` — ``"competitive"``,
    если ``n_beat`` покрывает большинство строк, иначе ``"behind"``.

    ``rows`` are sorted by metric name for determinism. ``n_beat`` counts rows
    where ``beats`` is true (ties included). ``verdict`` is ``"competitive"`` iff
    ``n_beat`` covers a majority of rows, else ``"behind"``.
    """

    rows: tuple[SotaRow, ...]
    n_beat: int
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready); ``rows`` becomes a list of dicts."""
        return {
            "rows": [r.as_dict() for r in self.rows],
            "n_beat": self.n_beat,
            "verdict": self.verdict,
        }


def compare(
    ours: Mapping[str, float],
    external: Mapping[str, tuple[str, float]],
    *,
    higher_is_better: Mapping[str, bool] | None = None,
) -> SotaComparison:
    """Compare ``ours`` to published ``external`` SOTA numbers → :class:`SotaComparison`.

    ``external`` сопоставляет метрике пару ``(имя_системы, значение)``. Метрика
    без внешнего числа игнорируется; внешнее число без нашей метрики — ``KeyError``.
    ``higher_is_better`` задаёт направление метрики (по умолчанию «больше — лучше»).
    ``delta = ours - external`` при «больше — лучше», иначе ``external - ours``,
    так что плюс всегда означает, что мы не хуже. ``beats`` истинно при
    ``delta >= 0``. Вердикт — ``"competitive"`` при большинстве обойдённых метрик.

    ``external`` maps a metric to an ``(system, value)`` pair. A metric with no
    external entry is skipped; an external entry with no matching ``ours`` metric
    raises :class:`KeyError`. ``higher_is_better`` sets each metric's direction
    (default: higher-is-better). ``delta`` is ``ours - external`` for
    higher-is-better metrics else ``external - ours``, so a positive value always
    means we are at least as good; ``beats`` is ``delta >= 0``. ``verdict`` is
    ``"competitive"`` iff we beat/tie a majority of metrics.
    """
    directions = higher_is_better or {}
    rows: list[SotaRow] = []
    n_beat = 0
    for metric in sorted(external):
        system, ext_value = external[metric]
        # Missing our-side metric raises KeyError here (loud, not silent).
        our_value = float(ours[metric])
        ext_value = float(ext_value)
        higher = bool(directions.get(metric, True))
        raw = our_value - ext_value if higher else ext_value - our_value
        delta = round(raw, _DELTA_NDIGITS)
        beats = delta >= 0.0
        rows.append(
            SotaRow(
                metric=metric,
                ours=our_value,
                external=ext_value,
                external_system=system,
                delta=delta,
                beats=beats,
            )
        )
        if beats:
            n_beat += 1
    verdict = _COMPETITIVE if n_beat >= _majority(len(rows)) else _BEHIND
    return SotaComparison(rows=tuple(rows), n_beat=n_beat, verdict=verdict)


def _majority(n_rows: int) -> int:
    """Smallest count that is a strict majority of ``n_rows`` (``0`` when empty).

    For ``n_rows == 3`` → ``2``; for ``n_rows == 0`` → ``0`` so an empty
    comparison is trivially ``"competitive"`` (nothing was lost).
    """
    return n_rows // 2 + 1 if n_rows else 0
