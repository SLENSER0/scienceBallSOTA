"""Tests for the runnable retrieval eval harness (§4.11 / §18.6).

Builds the real seed graph over a temp KuzuGraphStore and asserts hand-checked
Recall@k / MRR numbers for the keyword-overlap retriever.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_eval.retrieval_eval import (
    GOLDEN,
    QueryResult,
    RetrievalEvalReport,
    rank_entities,
    run_retrieval_eval,
)
from kg_eval.retrieval_metrics import RetrievalMetrics
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    try:
        yield s
    finally:
        s.close()


def test_harness_returns_per_query_and_aggregate(store) -> None:  # type: ignore[no-untyped-def]
    report = run_retrieval_eval(store)
    assert isinstance(report, RetrievalEvalReport)
    assert len(report.per_query) == len(GOLDEN)
    assert all(isinstance(q, QueryResult) for q in report.per_query)
    assert isinstance(report.aggregate, RetrievalMetrics)
    # the report round-trips to a plain dict {per_query, aggregate}
    d = report.as_dict()
    assert set(d) == {"k", "per_query", "aggregate"}
    assert len(d["per_query"]) == len(GOLDEN)
    assert set(d["aggregate"]) >= {"recall_at_k", "mrr", "ndcg_at_k"}


def test_golden_ids_exist_in_seed(store) -> None:  # type: ignore[no-untyped-def]
    # every relevant id in GOLDEN must reference a real seeded node (§3.17)
    for _query, relevant in GOLDEN:
        for rid in relevant:
            assert store.get_node(rid) is not None, rid


def test_perfect_golden_recall_at_1(store) -> None:  # type: ignore[no-untyped-def]
    # "ion exchange" (ионный обмен): its sole exact-token hit is the ion-exchange
    # solution, so recall@1 == mrr == 1.0 with the relevant id ranked first.
    golden = [("ion exchange", ("tech:ion-exchange-desalination",))]
    report = run_retrieval_eval(store, golden=golden, k=1)
    qr = report.per_query[0]
    assert qr.ranked_ids[0] == "tech:ion-exchange-desalination"
    assert qr.metrics.recall_at_k == 1.0
    assert qr.metrics.mrr == 1.0
    assert qr.metrics.hit_at_k == 1.0
    assert report.aggregate.recall_at_k == 1.0


def test_all_default_perfect_queries_rank_relevant_first(store) -> None:  # type: ignore[no-untyped-def]
    # queries 1..5 each have a single relevant id that must top the ranking;
    # their per-query MRR is therefore exactly 1.0 (hand-checked, §18.6).
    report = run_retrieval_eval(store, k=10)
    single = [q for q in report.per_query if len(q.relevant_ids) == 1]
    assert len(single) == 5
    for qr in single:
        assert qr.ranked_ids[0] == qr.relevant_ids[0]
        assert qr.metrics.mrr == 1.0
        assert qr.metrics.recall_at_k == 1.0


def test_flash_smelting_multi_relevant(store) -> None:  # type: ignore[no-untyped-def]
    # "flash smelting" (взвешенная плавка / ПВП) has 3 exact-token hits; two are
    # relevant. Deterministic id-sorted order is [equip, regime, tech, slag], so
    # the first relevant (regime) sits at rank 2 => MRR == 0.5, Recall@10 == 1.0.
    golden = [
        (
            "flash smelting",
            ("regime:flash-smelting-copper", "tech:flash-smelting-furnace-scheme"),
        )
    ]
    report = run_retrieval_eval(store, golden=golden, k=10)
    qr = report.per_query[0]
    assert qr.ranked_ids[:3] == (
        "equip:flash-smelting-furnace",
        "regime:flash-smelting-copper",
        "tech:flash-smelting-furnace-scheme",
    )
    assert qr.metrics.mrr == 0.5
    assert qr.metrics.recall_at_k == 1.0
    # at cutoff 1 only the non-relevant equipment node is seen -> recall@1 == 0
    report_k1 = run_retrieval_eval(store, golden=golden, k=1)
    assert report_k1.per_query[0].metrics.recall_at_k == 0.0


def test_aggregate_mrr_and_recall_in_unit_range(store) -> None:  # type: ignore[no-untyped-def]
    report = run_retrieval_eval(store)
    agg = report.aggregate
    assert 0.0 <= agg.mrr <= 1.0
    assert 0.0 <= agg.recall_at_k <= 1.0
    assert 0.0 <= agg.ndcg_at_k <= 1.0
    # 5 perfect queries (mrr 1.0) + flash smelting (mrr 0.5) => mean 0.9167
    assert agg.mrr == pytest.approx((5 * 1.0 + 0.5) / 6, abs=1e-4)


def test_empty_golden_handled(store) -> None:  # type: ignore[no-untyped-def]
    report = run_retrieval_eval(store, golden=[])
    assert report.per_query == ()
    # aggregate over zero runs is all-zero, not a crash
    assert report.aggregate.mrr == 0.0
    assert report.aggregate.recall_at_k == 0.0
    assert report.as_dict()["per_query"] == []


def test_rank_entities_blank_query_is_empty(store) -> None:  # type: ignore[no-untyped-def]
    assert rank_entities(store, "   ") == []
    # a query with no seed overlap ranks nothing
    assert rank_entities(store, "zzzqqq nonexistent term") == []


def test_rank_entities_drops_substring_only_noise(store) -> None:  # type: ignore[no-untyped-def]
    # "ion" is a substring of many words (concentration, distribution...) so the
    # CONTAINS prefilter returns noise, but exact-token scoring keeps only the
    # ion-exchange node for the "ion exchange" query.
    ranked = rank_entities(store, "ion exchange")
    assert ranked == ["tech:ion-exchange-desalination"]
