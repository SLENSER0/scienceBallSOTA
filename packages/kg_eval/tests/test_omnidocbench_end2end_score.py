"""Tests for the OmniDocBench end-to-end aggregator — тесты сводки (§23.34/§23.31)."""

from __future__ import annotations

import pytest

from kg_eval.omnidocbench_end2end_score import (
    DocScore,
    OmniDocReport,
    score_documents,
)


def test_single_doc_all_facets_perfect() -> None:
    """A single doc with every facet at 1.0 scores overall 1.0 (§23.34)."""
    report = score_documents(
        [{"doc_type": "paper", "text": 1.0, "table": 1.0, "formula": 1.0, "layout": 1.0}]
    )
    assert report.n == 1
    assert report.overall == 1.0
    assert report.by_type == {"paper": 1.0}
    assert report.worst_type == "paper"


def test_two_present_facets_equal_default_weights() -> None:
    """text=0.5, table=1.0 with equal default weights → doc overall 0.75 (§23.34)."""
    report = score_documents([{"doc_type": "paper", "text": 0.5, "table": 1.0}])
    assert report.overall == 0.75
    assert report.by_type == {"paper": 0.75}


def test_missing_formula_excluded_from_denominator() -> None:
    """Absent 'formula' is skipped, not counted as 0 — denominator is 2, not 3 (§23.34)."""
    # If formula were treated as 0.0, overall would be (0.5+1.0+0)/3 == 0.5.
    report = score_documents([{"doc_type": "paper", "text": 0.5, "table": 1.0}])
    assert report.overall == 0.75  # (0.5 + 1.0) / 2


def test_two_docs_same_type_average_into_by_type() -> None:
    """Two docs of one type average their overalls into by_type (§23.34)."""
    report = score_documents(
        [
            {"doc_type": "paper", "text": 1.0, "table": 1.0},  # overall 1.0
            {"doc_type": "paper", "text": 0.5, "table": 0.5},  # overall 0.5
        ]
    )
    assert report.by_type == {"paper": 0.75}
    assert report.overall == 0.75


def test_worst_type_picks_lowest_mean() -> None:
    """worst_type is the doc_type with the lowest mean overall (§23.34)."""
    report = score_documents(
        [
            {"doc_type": "paper", "text": 1.0},
            {"doc_type": "receipt", "text": 0.2},
            {"doc_type": "slides", "text": 0.9},
        ]
    )
    assert report.worst_type == "receipt"
    assert report.by_type["receipt"] == pytest.approx(0.2)


def test_worst_type_tie_breaks_alphabetically() -> None:
    """On a tie in mean overall, worst_type is the alphabetically first type (§23.34)."""
    report = score_documents(
        [
            {"doc_type": "zeta", "text": 0.3},
            {"doc_type": "alpha", "text": 0.3},
        ]
    )
    assert report.worst_type == "alpha"


def test_custom_weights_shift_overall() -> None:
    """weights text:3 table:1 shift a 0.5/1.0 doc to overall 0.625 (§23.34)."""
    report = score_documents(
        [{"doc_type": "paper", "text": 0.5, "table": 1.0}],
        weights={"text": 3, "table": 1},
    )
    # (0.5*3 + 1.0*1) / (3 + 1) = 2.5 / 4 = 0.625
    assert report.overall == 0.625


def test_unknown_weight_key_raises_keyerror() -> None:
    """A weight key outside the recognised facets raises KeyError (§23.34)."""
    with pytest.raises(KeyError):
        score_documents(
            [{"doc_type": "paper", "text": 1.0}],
            weights={"bogus": 2.0},
        )


def test_empty_docs_raises_valueerror() -> None:
    """An empty document sequence raises ValueError (§23.34)."""
    with pytest.raises(ValueError):
        score_documents([])


def test_missing_facet_key_raises_nothing() -> None:
    """A doc carrying only one facet scores fine — no facet key is mandatory (§23.34)."""
    report = score_documents([{"doc_type": "paper", "layout": 0.8}])
    assert report.overall == pytest.approx(0.8)
    assert report.by_type == {"paper": pytest.approx(0.8)}


def test_report_as_dict_sorts_by_type() -> None:
    """OmniDocReport.as_dict emits by_type in sorted key order (§23.34)."""
    report = score_documents(
        [
            {"doc_type": "zeta", "text": 0.4},
            {"doc_type": "alpha", "text": 0.6},
            {"doc_type": "mu", "text": 0.5},
        ]
    )
    d = report.as_dict()
    assert list(d["by_type"].keys()) == ["alpha", "mu", "zeta"]
    assert d["n"] == 3
    assert d["worst_type"] == "zeta"


def test_docscore_as_dict_roundtrip() -> None:
    """DocScore.as_dict exposes doc_type, overall and the present facets (§23.34)."""
    ds = DocScore(doc_type="paper", overall=0.75, facets={"text": 0.5, "table": 1.0})
    assert ds.as_dict() == {
        "doc_type": "paper",
        "overall": 0.75,
        "facets": {"text": 0.5, "table": 1.0},
    }


def test_report_frozen_and_typed() -> None:
    """OmniDocReport is a frozen dataclass — mutation is rejected (§23.34)."""
    report = score_documents([{"doc_type": "paper", "text": 1.0}])
    assert isinstance(report, OmniDocReport)
    with pytest.raises(AttributeError):
        report.overall = 0.0  # type: ignore[misc]
