"""Spec-точная §12.4 per-source **contribution attribution** для fused-оценки.

Объясняет, какой ретривер (``dense`` / ``sparse`` / ``bm25`` /
``graph_proximity`` / ``evidence_quality``) «вытащил» документ в фьюзинге —
для прозрачности поиска (§17). Отдельно от:

- ``rerank_explain`` — дельты reranker'а (изменение ранга после rerank);
- ``retrieval_trace`` — тайминги стадий поиска.

Здесь считается вклад каждого источника в итоговую взвешенную сумму:
``contribution[s] = components[s] * weights[s]``; доли ``shares[s]`` —
нормировка вкладов к ``total``; ``dominant`` — источник с максимальным вкладом
(ничьи разрешаются по имени лексикографически по возрастанию).

Pure python — no store/graph access; caller собирает словари компонентов и весов.
Kuzu note: custom node props не являются queryable-колонками — caller делает
``RETURN`` по базовым колонкам и читает остальное через ``get_node()`` до сборки
словарей; тесты строят временный store при необходимости.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ContributionBreakdown:
    """Разбор вклада источников для одного документа (§12.4 / §17).

    Атрибуты:
        doc_id:        идентификатор документа.
        total:         итоговая fused-оценка (сумма вкладов).
        contributions: вклад каждого источника ``components[s] * weights[s]``.
        shares:        доля источника в ``total`` (0.0 при ``total == 0``).
        dominant:      источник с максимальным вкладом (ничьи — по имени возр.).
    """

    doc_id: str
    total: float
    contributions: dict[str, float]
    shares: dict[str, float]
    dominant: str

    def as_dict(self) -> dict:
        """Round-trip всех полей в обычный ``dict`` (для JSON/логов/UI)."""
        return {
            "doc_id": self.doc_id,
            "total": self.total,
            "contributions": dict(self.contributions),
            "shares": dict(self.shares),
            "dominant": self.dominant,
        }


def attribute(
    doc_id: str,
    components: Mapping[str, float],
    weights: Mapping[str, float],
) -> ContributionBreakdown:
    """Атрибутировать fused-оценку одного документа по источникам (§12.4).

    Для каждого источника ``s`` из ``components``:
    ``contribution[s] = components[s] * weights.get(s, 0.0)`` — источник,
    отсутствующий в ``weights``, вносит ``0.0``. ``total`` — сумма вкладов;
    ``shares[s] = contribution[s] / total`` (все ``0.0`` при ``total == 0`` —
    без деления на ноль). ``dominant`` — источник с максимальным вкладом, ничьи
    разрешаются по имени лексикографически (меньшее имя раньше). Пустые
    ``components`` → ``dominant == ""``.
    """
    contributions: dict[str, float] = {
        source: float(value) * float(weights.get(source, 0.0))
        for source, value in components.items()
    }
    total = float(sum(contributions.values()))
    if total == 0.0:
        shares = dict.fromkeys(contributions, 0.0)
    else:
        shares = {source: value / total for source, value in contributions.items()}

    # Доминирующий источник: максимальный вклад, ничьи — по имени (возрастание).
    dominant = ""
    if contributions:
        dominant = min(contributions, key=lambda s: (-contributions[s], s))

    return ContributionBreakdown(
        doc_id=doc_id,
        total=total,
        contributions=contributions,
        shares=shares,
        dominant=dominant,
    )


def attribute_many(
    rows: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
) -> list[ContributionBreakdown]:
    """Атрибутировать множество документов и отсортировать по ``total`` убыв. (§12.4).

    ``rows`` — отображение ``doc_id -> components``; каждый разбирается через
    :func:`attribute` с общими ``weights``. Результат отсортирован по убыванию
    ``total``, ничьи — по ``doc_id`` (лексикографически, возрастание).
    """
    breakdowns = [attribute(doc_id, components, weights) for doc_id, components in rows.items()]
    breakdowns.sort(key=lambda b: (-b.total, b.doc_id))
    return breakdowns
