"""Eval report assembly — three metric blocks → one report (§18.7)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from kg_eval.report import EvalReport, build_report

# Representative real block shapes (as_dict outputs of the sibling metric modules).
RETRIEVAL = {  # kg_eval.retrieval_metrics.RetrievalMetrics.as_dict()
    "k": 10,
    "recall_at_k": 0.6667,
    "precision_at_k": 0.5,
    "hit_at_k": 1.0,
    "mrr": 0.75,
    "ndcg_at_k": 0.8,
    "average_precision": 0.75,
}
EXTRACTION = {  # kg_eval.gap_metrics.PRF.as_dict()
    "precision": 0.5,
    "recall": 0.5,
    "f1": 0.5,
    "tp": 1,
    "fp": 1,
    "fn": 1,
}
ANSWER = {  # aggregate over kg_eval.metrics.CaseResult
    "cases": 6,
    "passed": 6,
    "pass_rate": 1.0,
    "mean_entity_recall": 0.9167,
}


def test_build_report_carries_all_three_blocks() -> None:
    rep = build_report(retrieval=RETRIEVAL, extraction=EXTRACTION, answer=ANSWER)
    assert isinstance(rep, EvalReport)
    assert rep.retrieval == RETRIEVAL
    assert rep.extraction == EXTRACTION
    assert rep.answer == ANSWER
    # blocks are copied, not aliased — mutating the source leaves the report intact.
    assert rep.retrieval is not RETRIEVAL


def test_as_dict_shape_and_values() -> None:
    rep = build_report(
        retrieval=RETRIEVAL,
        extraction=EXTRACTION,
        answer=ANSWER,
        git_sha="abc123",
        dataset_version="v3",
    )
    d = rep.as_dict()
    assert set(d) == {"retrieval", "extraction", "answer", "generated_from"}
    assert d["retrieval"] == RETRIEVAL
    assert d["extraction"] == EXTRACTION
    assert d["answer"] == ANSWER
    assert d["generated_from"] == "git_sha=abc123; dataset_version=v3"


def test_to_json_round_trip() -> None:
    rep = build_report(
        retrieval=RETRIEVAL,
        extraction=EXTRACTION,
        answer=ANSWER,
        git_sha="deadbeef",
        dataset_version="golden-2026-07",
    )
    parsed = json.loads(rep.to_json())
    assert parsed == rep.as_dict()
    # nested numeric values survive the round-trip exactly.
    assert parsed["retrieval"]["mrr"] == 0.75
    assert parsed["extraction"]["tp"] == 1
    assert parsed["answer"]["pass_rate"] == 1.0


def test_to_markdown_contains_each_heading_and_a_metric_value() -> None:
    md = build_report(retrieval=RETRIEVAL, extraction=EXTRACTION, answer=ANSWER).to_markdown()
    # every block heading present (RU + EN).
    assert "## Retrieval / Поиск" in md
    assert "## Extraction / Извлечение" in md
    assert "## Answer / Ответ" in md
    # a concrete metric value from each block surfaces in the tables.
    assert "0.6667" in md  # retrieval recall_at_k
    assert "0.5" in md  # extraction f1
    assert "0.9167" in md  # answer mean_entity_recall
    # flattened metric keys appear as table rows.
    assert "| recall_at_k | 0.6667 |" in md
    assert "| pass_rate | 1.0 |" in md


def test_git_sha_and_dataset_version_in_every_output() -> None:
    rep = build_report(git_sha="feedcafe", dataset_version="ds-42")
    assert rep.generated_from == "git_sha=feedcafe; dataset_version=ds-42"
    assert "feedcafe" in rep.generated_from and "ds-42" in rep.generated_from
    for blob in (rep.to_json(), rep.to_markdown()):
        assert "feedcafe" in blob
        assert "ds-42" in blob


def test_empty_blocks_are_graceful() -> None:
    rep = build_report()  # nothing supplied
    assert rep.retrieval == {} and rep.extraction == {} and rep.answer == {}
    assert rep.generated_from == "git_sha=; dataset_version="
    md = rep.to_markdown()
    # each empty block still renders its heading + a placeholder, never crashes.
    assert md.count("_No metrics / Нет метрик._") == 3
    assert "## Retrieval / Поиск" in md
    # json round-trips with empty blocks too.
    assert json.loads(rep.to_json()) == rep.as_dict()


def test_deterministic_outputs() -> None:
    a = build_report(retrieval=RETRIEVAL, extraction=EXTRACTION, answer=ANSWER, git_sha="s")
    b = build_report(retrieval=RETRIEVAL, extraction=EXTRACTION, answer=ANSWER, git_sha="s")
    assert a.as_dict() == b.as_dict()
    assert a.to_json() == b.to_json()
    assert a.to_markdown() == b.to_markdown()
    # idempotent within a single instance as well.
    assert a.to_markdown() == a.to_markdown()


def test_nested_metric_block_is_flattened_in_table() -> None:
    # kg_eval.retrieval_eval.RetrievalEvalReport.as_dict() nests an "aggregate" block.
    nested = {"k": 10, "aggregate": {"mrr": 0.5, "recall_at_k": 0.8}}
    md = build_report(retrieval=nested).to_markdown()
    assert "| aggregate.mrr | 0.5 |" in md
    assert "| aggregate.recall_at_k | 0.8 |" in md
    assert "| k | 10 |" in md
    # the raw dotted-key JSON still round-trips (flattening is render-only).
    assert build_report(retrieval=nested).as_dict()["retrieval"] == nested


def test_report_is_frozen() -> None:
    rep = build_report(retrieval=RETRIEVAL)
    with pytest.raises(FrozenInstanceError):
        rep.generated_from = "mutated"  # type: ignore[misc]
