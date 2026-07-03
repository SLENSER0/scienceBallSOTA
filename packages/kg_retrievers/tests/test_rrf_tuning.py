"""Hand-checked tests for RRF ``k`` grid-search tuning (§12.4).

Каждое ожидаемое число посчитано вручную по формуле RRF ``1/(k+rank)`` и
``recall@n = |top_n ∩ gold| / |gold|``.

Fixture ``_CROSSOVER`` — два канала с известной точкой пересечения:

    channel A: [P, a1..a8, Q]   → P rank 1, Q rank 10
    channel B: [b1..b9, Q]      → Q rank 10

P встречается один раз в топе: score ``1/(k+1)``.
Q встречается дважды на ранге 10: score ``2/(k+10)``.
Кроссовер: P > Q ⇔ k < 8; при k == 8 — ничья (P раньше по first-appearance).
"""

from __future__ import annotations

import pytest

from kg_retrievers.rrf_tuning import (
    DEFAULT_RECALL_N,
    GridSearchResult,
    grid_search_k,
    recall_at_n,
)

_CROSSOVER: dict[str, list[str]] = {
    "A": ["P", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "Q"],
    "B": ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9", "Q"],
}


# ---------------------------------------------------------------------------
# recall_at_n — базовая метрика
# ---------------------------------------------------------------------------


def test_recall_at_n_basic_fraction() -> None:
    """top3 = {a,b,c}; gold = {b,d,x}; hit только b → recall = 1/3."""
    ranked = ["a", "b", "c", "d"]
    assert recall_at_n(ranked, {"b", "d", "x"}, n=3) == pytest.approx(1.0 / 3.0)


def test_recall_at_n_perfect_and_cutoff() -> None:
    """n=4 ловит и d → recall 2/3; n=1 ловит только a (не в gold) → 0.0."""
    ranked = ["a", "b", "c", "d"]
    assert recall_at_n(ranked, {"b", "d", "x"}, n=4) == pytest.approx(2.0 / 3.0)
    assert recall_at_n(ranked, {"b", "d", "x"}, n=1) == 0.0


def test_recall_at_n_empty_gold_is_zero() -> None:
    """Пустой gold — нечего находить → recall 0.0 (не деление на ноль)."""
    assert recall_at_n(["a", "b"], set(), n=2) == 0.0


def test_recall_at_n_nonpositive_n_raises() -> None:
    """n должен быть положителен."""
    with pytest.raises(ValueError, match="recall n must be positive"):
        recall_at_n(["a"], {"a"}, n=0)


# ---------------------------------------------------------------------------
# grid_search_k — перебор k
# ---------------------------------------------------------------------------


def test_grid_search_best_k_after_crossover() -> None:
    """gold={Q}, n=1: k=5,8 → P сверху (recall 0); k=20 → Q сверху (recall 1)."""
    res = grid_search_k(_CROSSOVER, {"Q"}, ks=[5, 8, 20], n=1)
    assert isinstance(res, GridSearchResult)
    assert res.best_k == 20
    assert res.scores == {5: 0.0, 8: 0.0, 20: 1.0}


def test_grid_search_scores_per_k_handchecked() -> None:
    """Проверяем recall на каждом k отдельно (P=1/(k+1) vs Q=2/(k+10))."""
    res = grid_search_k(_CROSSOVER, {"Q"}, ks=[7, 8, 9], n=1)
    # k=7: P=1/8=0.125 > Q=2/17≈0.1176 → P top → 0.0
    # k=8: P=1/9 == Q=2/18 → ничья, P раньше → 0.0
    # k=9: P=1/10=0.1 < Q=2/19≈0.1053 → Q top → 1.0
    assert res.scores == {7: 0.0, 8: 0.0, 9: 1.0}
    assert res.best_k == 9


def test_grid_search_tie_prefers_smallest_k() -> None:
    """n=10 ловит Q при любом k → все recall 1.0 → ties → наименьший k."""
    res = grid_search_k(_CROSSOVER, {"Q"}, ks=[30, 5, 20], n=10)
    assert res.scores == {30: 1.0, 5: 1.0, 20: 1.0}
    assert res.best_k == 5  # ties разрешаются наименьшим k


def test_grid_search_empty_gold_all_zero() -> None:
    """Пустой gold → recall 0.0 на всех k → best_k = наименьший k."""
    res = grid_search_k(_CROSSOVER, set(), ks=[60, 10], n=5)
    assert res.scores == {60: 0.0, 10: 0.0}
    assert res.best_k == 10


def test_grid_search_empty_ks_raises() -> None:
    """Пустой список k — нечего перебирать."""
    with pytest.raises(ValueError, match="ks must not be empty"):
        grid_search_k(_CROSSOVER, {"Q"}, ks=[])


def test_grid_search_default_n() -> None:
    """n по умолчанию = DEFAULT_RECALL_N; фиксируется в результате."""
    res = grid_search_k(_CROSSOVER, {"Q"}, ks=[60])
    assert res.n == DEFAULT_RECALL_N == 10


def test_grid_search_result_as_dict() -> None:
    """as_dict — плоская проекция; scores — копия (мутация не протекает)."""
    res = grid_search_k(_CROSSOVER, {"Q"}, ks=[20], n=1)
    d = res.as_dict()
    assert d == {"best_k": 20, "n": 1, "scores": {20: 1.0}}
    d["scores"][20] = -1.0
    assert res.scores[20] == 1.0  # внутреннее состояние не затронуто
