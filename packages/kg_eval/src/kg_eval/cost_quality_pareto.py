"""Cost/quality Pareto-frontier selection over configurations (§23.10/§23.31).

Выбирает Парето-фронт по парам (стоимость, качество): меньшая стоимость и большее
качество — лучше. Конфигурация ``A`` доминируется, если существует ``B`` с
``cost <= A.cost`` и ``quality >= A.quality`` и хотя бы одним строгим неравенством.
Фронт — недоминируемые конфигурации, отсортированные по стоимости по возрастанию,
затем по качеству по убыванию. «Колено» (knee) — точка фронта с максимальным
отношением ``quality/cost``; если фронт пуст — ``None``; если у какой-либо точки
фронта ``cost <= 0`` — берётся точка с максимальным качеством. Это НЕ
:mod:`cost_per_query_report` (учёт одной конфигурации): здесь сравнение множества
конфигураций и отбор недоминируемых.

Selects a Pareto frontier over (cost, quality) pairs: lower cost and higher quality
are better. A config ``A`` is dominated iff some ``B`` has ``cost <= A.cost`` and
``quality >= A.quality`` with at least one strict inequality. The frontier is the
non-dominated configs sorted by cost ascending, then quality descending. The knee is
the frontier point maximizing ``quality/cost``; ``None`` if the frontier is empty; if
any frontier point has ``cost <= 0`` the max-quality point is picked instead. Distinct
from :mod:`cost_per_query_report` (single-config accounting): this compares many configs
and keeps the non-dominated ones.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigPoint:
    """Одна конфигурация с вердиктом доминирования (§23.10/§23.31).

    ``dominated`` is true iff at least one other config dominates this one.
    ``dominated_by`` lists the names of the dominating configs, sorted by name
    (empty when this point is on the frontier).
    """

    name: str
    cost: float
    quality: float
    dominated: bool
    dominated_by: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready), 5 keys."""
        return {
            "name": self.name,
            "cost": self.cost,
            "quality": self.quality,
            "dominated": self.dominated,
            "dominated_by": list(self.dominated_by),
        }


@dataclass(frozen=True)
class ParetoReport:
    """Итог отбора Парето — фронт, доминируемые и «колено» (§23.10/§23.31).

    ``frontier`` are the non-dominated names sorted by cost ascending then quality
    descending. ``dominated`` are the dominated names sorted the same way. ``knee``
    is the chosen frontier point name (``None`` if the frontier is empty).
    """

    frontier: tuple[str, ...]
    dominated: tuple[str, ...]
    knee: str | None

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready), 3 keys."""
        return {
            "frontier": list(self.frontier),
            "dominated": list(self.dominated),
            "knee": self.knee,
        }


def _strictly_dominates(b_cost: float, b_quality: float, a_cost: float, a_quality: float) -> bool:
    """True iff ``B`` dominates ``A``: ``cost<=`` and ``quality>=`` with one strict."""
    if b_cost <= a_cost and b_quality >= a_quality:
        return b_cost < a_cost or b_quality > a_quality
    return False


def compute_points(configs: Mapping[str, Mapping[str, float]]) -> tuple[ConfigPoint, ...]:
    """Build a :class:`ConfigPoint` per config with domination verdicts (§23.10/§23.31).

    Каждая конфигурация ``A`` доминируется, если существует другая ``B`` с
    ``cost <= A.cost`` и ``quality >= A.quality`` и хотя бы одним строгим
    неравенством. Идентичные дубликаты не доминируют друг друга (нет строгого
    неравенства). Результат отсортирован по стоимости по возрастанию, затем по
    качеству по убыванию, затем по имени. Пустой вход — ``ValueError``.

    Each config ``A`` is dominated when some other ``B`` has ``cost <= A.cost`` and
    ``quality >= A.quality`` with at least one strict inequality. Identical duplicates
    do not dominate each other (no strict inequality). Output is sorted by cost
    ascending, then quality descending, then name. Empty input raises ``ValueError``.
    """
    if not configs:
        raise ValueError("configs must not be empty")

    items = [(name, float(c["cost"]), float(c["quality"])) for name, c in configs.items()]
    points: list[ConfigPoint] = []
    for a_name, a_cost, a_quality in items:
        dominators = sorted(
            b_name
            for b_name, b_cost, b_quality in items
            if b_name != a_name and _strictly_dominates(b_cost, b_quality, a_cost, a_quality)
        )
        points.append(
            ConfigPoint(
                name=a_name,
                cost=a_cost,
                quality=a_quality,
                dominated=bool(dominators),
                dominated_by=tuple(dominators),
            )
        )
    points.sort(key=lambda p: (p.cost, -p.quality, p.name))
    return tuple(points)


def _pick_knee(frontier: tuple[ConfigPoint, ...]) -> str | None:
    """Frontier point maximizing ``quality/cost`` (max quality if any ``cost<=0``)."""
    if not frontier:
        return None
    if any(p.cost <= 0.0 for p in frontier):
        # Ratio is ill-defined with non-positive cost: fall back to best quality.
        return max(frontier, key=lambda p: p.quality).name
    return max(frontier, key=lambda p: p.quality / p.cost).name


def compute_pareto(configs: Mapping[str, Mapping[str, float]]) -> ParetoReport:
    """Compute the Pareto :class:`ParetoReport` over ``configs`` (§23.10/§23.31).

    Отбирает недоминируемые конфигурации во фронт (сортировка по стоимости по
    возрастанию, затем по качеству по убыванию), собирает доминируемые в том же
    порядке и выбирает «колено» — точку фронта с максимальным ``quality/cost``
    (или максимальным качеством, если у какой-либо точки фронта ``cost <= 0``).
    Пустой вход — ``ValueError``.

    Selects the non-dominated configs into the frontier (sorted by cost ascending
    then quality descending), collects the dominated ones in the same order, and picks
    the knee — the frontier point maximizing ``quality/cost`` (or maximum quality if
    any frontier point has ``cost <= 0``). Empty input raises ``ValueError``.
    """
    points = compute_points(configs)  # raises ValueError on empty
    frontier = tuple(p for p in points if not p.dominated)
    dominated = tuple(p for p in points if p.dominated)
    return ParetoReport(
        frontier=tuple(p.name for p in frontier),
        dominated=tuple(p.name for p in dominated),
        knee=_pick_knee(frontier),
    )
