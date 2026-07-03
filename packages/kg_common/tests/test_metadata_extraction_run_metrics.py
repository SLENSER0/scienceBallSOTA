"""Tests for MLflow extraction-run metrics — тесты метрик прогона (§10.13)."""

from __future__ import annotations

from kg_common.metadata.extraction_run_metrics import (
    ExtractionRunMetrics,
    compute,
    mlflow_metrics,
    mlflow_params,
)


def _char(start: int | None, end: int | None) -> dict[str, object]:
    return {"char_start": start, "char_end": end}


def test_empty_evidence_yields_zero_ratio() -> None:
    m = compute("regex", "gpt", "v1", triples=[("s", "p", "o")], evidence=[])
    assert m.n_evidence == 0
    assert m.evidence_span_ratio == 0.0
    assert m.n_evidence_with_span == 0


def test_two_full_char_spans_ratio_one() -> None:
    ev = [_char(0, 5), _char(10, 20)]
    m = compute("regex", "gpt", "v1", triples=[1, 2], evidence=ev)
    assert m.n_evidence == 2
    assert m.n_evidence_with_span == 2
    assert m.evidence_span_ratio == 1.0


def test_four_evidence_one_span_ratio_quarter() -> None:
    ev = [_char(0, 5), _char(1, None), _char(None, None), {"note": "x"}]
    m = compute("regex", "gpt", "v1", triples=[], evidence=ev)
    assert m.n_evidence == 4
    assert m.n_evidence_with_span == 1
    assert m.evidence_span_ratio == 0.25


def test_char_start_without_end_is_not_counted() -> None:
    m = compute("regex", "gpt", "v1", triples=[], evidence=[_char(3, None)])
    assert m.n_evidence_with_span == 0
    assert m.evidence_span_ratio == 0.0


def test_char_end_without_start_is_not_counted() -> None:
    m = compute("regex", "gpt", "v1", triples=[], evidence=[_char(None, 9)])
    assert m.n_evidence_with_span == 0


def test_table_row_col_counts_as_span() -> None:
    m = compute("regex", "gpt", "v1", triples=[], evidence=[{"row": 2, "col": 4}])
    assert m.n_evidence_with_span == 1
    assert m.evidence_span_ratio == 1.0


def test_table_row_without_col_is_not_counted() -> None:
    m = compute("regex", "gpt", "v1", triples=[], evidence=[{"row": 2, "col": None}])
    assert m.n_evidence_with_span == 0


def test_zero_char_offsets_count_as_span() -> None:
    # 0 is a valid offset — only ``None`` disqualifies a span.
    m = compute("regex", "gpt", "v1", triples=[], evidence=[_char(0, 0)])
    assert m.n_evidence_with_span == 1


def test_mlflow_params_has_exactly_three_string_keys() -> None:
    m = compute("regex", "gpt", "v1", triples=[1], evidence=[])
    params = mlflow_params(m)
    assert set(params) == {"extractor", "model", "prompt_version"}
    assert len(params) == 3
    assert all(isinstance(v, str) for v in params.values())
    assert params == {"extractor": "regex", "model": "gpt", "prompt_version": "v1"}


def test_mlflow_metrics_n_triples_matches_len() -> None:
    triples = [("a", "b", "c"), ("d", "e", "f"), ("g", "h", "i")]
    m = compute("regex", "gpt", "v1", triples=triples, evidence=[_char(0, 1)])
    metrics = mlflow_metrics(m)
    assert metrics["n_triples"] == float(len(triples))
    assert metrics["n_evidence"] == 1.0
    assert metrics["evidence_span_ratio"] == 1.0
    assert all(isinstance(v, float) for v in metrics.values())


def test_as_dict_round_trips_all_seven_fields() -> None:
    m = compute("regex", "gpt", "v1", triples=[1, 2], evidence=[_char(0, 3), {"row": 1, "col": 1}])
    d = m.as_dict()
    assert d == {
        "extractor": "regex",
        "model": "gpt",
        "prompt_version": "v1",
        "n_triples": 2,
        "n_evidence": 2,
        "n_evidence_with_span": 2,
        "evidence_span_ratio": 1.0,
    }
    assert ExtractionRunMetrics(**d) == m
    assert len(d) == 7


def test_ratio_is_rounded_to_six_places() -> None:
    ev = [_char(0, 1), {"note": "x"}, {"note": "y"}]
    m = compute("regex", "gpt", "v1", triples=[], evidence=ev)
    assert m.evidence_span_ratio == round(1 / 3, 6)
