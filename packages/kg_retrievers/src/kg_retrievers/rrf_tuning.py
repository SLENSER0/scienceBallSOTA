"""RRF constant tuning via recall@n grid search (§12.4 companion).

Строит ПОВЕРХ :mod:`kg_retrievers.fusion` (переиспользует :func:`rrf_fuse`,
не меняя его): перебирает набор кандидатов ``k`` для Reciprocal Rank Fusion и
выбирает тот, что максимизирует простой ``recall@n`` по золотому набору id.

Grid search over RRF ``k`` (§7.5 Node 6 / §12.4 ``rrf_k``): for each candidate
``k`` we fuse the channel rankings, take the top-``n`` fused ids, and score
``recall@n = |top_n ∩ gold| / |gold|``. Победитель — наибольший recall; ties
разрешаются наименьшим ``k`` (детерминизм, «дешевле» — меньший знаменатель).

Pure python — no store/graph access; callers assemble the ranking dicts.
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before building the rankings.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from kg_retrievers.fusion import rrf_fuse

# Default cutoff for recall@n if the caller does not pass one (§12.4).
DEFAULT_RECALL_N: int = 10


def recall_at_n(ranked_ids: Sequence[str], gold: Iterable[str], n: int) -> float:
    """Simple ``recall@n``: доля золотых id, попавших в топ-``n`` (§12.4).

    ``recall@n = |top_n ∩ gold| / |gold|``. Пустой ``gold`` → ``0.0`` (нечего
    находить). ``n`` must be positive; only the first ``n`` ranked ids count.
    """
    if n <= 0:
        raise ValueError(f"recall n must be positive, got {n!r}")
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    top = set(ranked_ids[:n])
    hits = sum(1 for g in gold_set if g in top)
    return hits / len(gold_set)


@dataclass(frozen=True)
class GridSearchResult:
    """Итог перебора ``k``: победитель ``best_k`` + ``scores`` (recall на каждый k)."""

    best_k: int
    n: int
    scores: dict[int, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Plain-dict projection for config/telemetry (§12.4)."""
        return {"best_k": self.best_k, "n": self.n, "scores": dict(self.scores)}


def grid_search_k(
    rankings: dict[str, list[str]],
    gold: Iterable[str],
    ks: Sequence[int],
    *,
    n: int = DEFAULT_RECALL_N,
) -> GridSearchResult:
    """Grid-search RRF ``k`` maximizing ``recall@n`` over ``gold`` (§12.4).

    Для каждого ``k`` из ``ks`` фьюзим ``rankings`` через :func:`rrf_fuse`,
    берём топ-``n`` id и считаем :func:`recall_at_n`. ``best_k`` — k с макс.
    recall; ties → наименьший ``k``. ``ks`` не должен быть пустым; значения
    ``k`` должны быть положительны (иначе :func:`rrf_fuse` поднимет ошибку).
    """
    if not ks:
        raise ValueError("ks must not be empty")
    gold_set = set(gold)
    scores: dict[int, float] = {}
    for k in ks:
        ranked = rrf_fuse(rankings, k=k)  # list[(id, score)], ranked desc
        ranked_ids = [cid for cid, _ in ranked]
        scores[k] = recall_at_n(ranked_ids, gold_set, n)
    # Победитель: max recall, ties → наименьший k (детерминированно).
    best_k = min(scores, key=lambda k: (-scores[k], k))
    return GridSearchResult(best_k=best_k, n=n, scores=scores)
