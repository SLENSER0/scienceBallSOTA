"""Tests for :mod:`kg_eval.cost_per_query_report` (§23.10).

Проверяем группировку по ``query_id``, суммы, среднее, p95 (ближайший ранг),
проверку бюджета и форму ``as_dict``. Все числа выбраны для ручной проверки.
"""

from __future__ import annotations

from kg_eval.cost_per_query_report import CostReport, aggregate


def test_two_calls_same_query_summed_into_one_query() -> None:
    """Две записи с одним ``query_id`` дают один запрос с суммарной стоимостью."""
    records = [
        {"query_id": "q1", "cost_usd": 0.02, "tokens": 100},
        {"query_id": "q1", "cost_usd": 0.03, "tokens": 150},
    ]
    report = aggregate(records)
    assert report.n_queries == 1
    assert report.mean_cost_per_query == 0.05
    assert report.total_cost_usd == 0.05


def test_n_queries_counts_distinct_query_ids() -> None:
    """``n_queries`` считает различные ``query_id`` (три вызова, два запроса)."""
    records = [
        {"query_id": "q1", "cost_usd": 0.01, "tokens": 10},
        {"query_id": "q2", "cost_usd": 0.02, "tokens": 20},
        {"query_id": "q1", "cost_usd": 0.01, "tokens": 10},
    ]
    report = aggregate(records)
    assert report.n_queries == 2


def test_empty_input_zeros_and_not_over_budget() -> None:
    """Пустой вход — все нули и ``over_budget=False`` даже с бюджетом."""
    report = aggregate([], budget_per_query=0.01)
    assert report.n_queries == 0
    assert report.total_cost_usd == 0.0
    assert report.mean_cost_per_query == 0.0
    assert report.p95_cost_per_query == 0.0
    assert report.total_tokens == 0
    assert report.over_budget is False


def test_p95_of_single_query_equals_that_query_cost() -> None:
    """p95 для одного запроса равен стоимости этого запроса."""
    records = [{"query_id": "q1", "cost_usd": 0.07, "tokens": 5}]
    report = aggregate(records)
    assert report.p95_cost_per_query == 0.07


def test_mean_over_budget_true() -> None:
    """Среднее 0.05 при бюджете 0.04 → ``over_budget=True``."""
    records = [{"query_id": "q1", "cost_usd": 0.05, "tokens": 1}]
    report = aggregate(records, budget_per_query=0.04)
    assert report.mean_cost_per_query == 0.05
    assert report.over_budget is True


def test_budget_none_always_not_over_budget() -> None:
    """Без бюджета (``None``) ``over_budget`` всегда ложно даже при высокой цене."""
    records = [{"query_id": "q1", "cost_usd": 9.99, "tokens": 1}]
    report = aggregate(records, budget_per_query=None)
    assert report.over_budget is False


def test_total_tokens_sums_across_all_records() -> None:
    """``total_tokens`` суммирует токены всех записей независимо от запроса."""
    records = [
        {"query_id": "q1", "cost_usd": 0.01, "tokens": 100},
        {"query_id": "q1", "cost_usd": 0.01, "tokens": 200},
        {"query_id": "q2", "cost_usd": 0.01, "tokens": 300},
    ]
    report = aggregate(records)
    assert report.total_tokens == 600


def test_p95_nearest_rank_over_many_queries() -> None:
    """p95 по 20 запросам с ценами 1..20 = 19-я по рангу (ceil(0.95*20)=19)."""
    records = [{"query_id": f"q{i}", "cost_usd": float(i), "tokens": 0} for i in range(1, 21)]
    report = aggregate(records)
    assert report.n_queries == 20
    assert report.p95_cost_per_query == 19.0


def test_as_dict_has_seven_keys_usd_rounded_to_6dp() -> None:
    """``as_dict`` содержит 7 ключей; USD-поля округлены до 6 знаков."""
    records = [{"query_id": "q1", "cost_usd": 0.1234567, "tokens": 3}]
    report = aggregate(records, budget_per_query=1.0)
    d = report.as_dict()
    assert len(d) == 7
    assert set(d) == {
        "n_queries",
        "total_cost_usd",
        "mean_cost_per_query",
        "p95_cost_per_query",
        "total_tokens",
        "budget_per_query",
        "over_budget",
    }
    assert d["total_cost_usd"] == 0.123457
    assert d["mean_cost_per_query"] == 0.123457
    assert d["p95_cost_per_query"] == 0.123457


def test_returns_cost_report_instance() -> None:
    """Возврат — экземпляр :class:`CostReport`."""
    assert isinstance(aggregate([]), CostReport)
