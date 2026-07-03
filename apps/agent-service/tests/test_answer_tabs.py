"""Hand-checked tests for §13.17 answer tab-structure + aggregates builder.

Pure-python, no store / no LLM: hand :func:`build_tabs` / :func:`aggregate_counts`
/ :func:`effect_range` plain-dict state fields (§13.11) and assert the exact
§5.2.2 tab shape and numeric aggregates. Каждое ожидаемое значение выписано
явно, чтобы тест проверялся руками.
"""

from __future__ import annotations

import pytest
from agent_service.answer_tabs import (
    AnswerTabs,
    aggregate_counts,
    build_tabs,
    effect_range,
)

# The six §5.2.2 tab keys every layout must carry.
_TAB_KEYS = {"summary", "experiments", "evidence", "graph", "gaps", "contradictions"}


def _state() -> dict[str, object]:
    """A representative agent state: 3 experiments, 3 evidence rows, 2 gaps."""
    return {
        "retrieved_experiments": [
            {"property_name": "band_gap", "effect": 0.12},
            {"property_name": "band_gap", "effect": 0.28},
            {"property_name": "band_gap", "effect": 0.20},
        ],
        "evidence": [
            {"doc_id": "doc:p1", "evidence_id": "ev:1"},
            {"doc_id": "doc:p1", "evidence_id": "ev:2"},
            {"doc_id": "doc:p2", "evidence_id": "ev:3"},
        ],
        "visualization_payload": {"nodes": [], "edges": []},
        "gaps": [
            {"type": "missing_baseline", "field": "control"},
            {"type": "missing_property", "field": "hardness"},
        ],
        "contradictions": [{"claimA": "c1", "claimB": "c2"}],
    }


# ---------------------------------------------------------------------------
# (1) all six tab keys present
# ---------------------------------------------------------------------------
def test_build_tabs_has_all_six_tab_keys() -> None:
    tabs = build_tabs(_state()).as_dict()
    assert set(tabs) == _TAB_KEYS


# ---------------------------------------------------------------------------
# (2) effect_range over matching rows → (min, max)
# ---------------------------------------------------------------------------
def test_effect_range_min_max() -> None:
    rows = [
        {"property_name": "band_gap", "effect": 0.12},
        {"property_name": "band_gap", "effect": 0.28},
        {"property_name": "band_gap", "effect": 0.20},
    ]
    assert effect_range(rows, "band_gap") == (0.12, 0.28)


def test_effect_range_ignores_other_properties() -> None:
    rows = [
        {"property_name": "band_gap", "effect": 0.12},
        {"property_name": "conductivity", "effect": 9.9},
        {"property_name": "band_gap", "effect": 0.28},
    ]
    # only band_gap effects (0.12, 0.28) count; the conductivity 9.9 is excluded.
    assert effect_range(rows, "band_gap") == (0.12, 0.28)


# ---------------------------------------------------------------------------
# (3) effect_range with no matching property → None
# ---------------------------------------------------------------------------
def test_effect_range_no_match_is_none() -> None:
    rows = [{"property_name": "band_gap", "effect": 0.12}]
    assert effect_range(rows, "hardness") is None
    assert effect_range([], "band_gap") is None


def test_effect_range_non_numeric_effect_skipped() -> None:
    # a row matching the property but with a non-numeric / bool effect is ignored.
    rows = [
        {"property_name": "band_gap", "effect": None},
        {"property_name": "band_gap", "effect": True},
    ]
    assert effect_range(rows, "band_gap") is None


# ---------------------------------------------------------------------------
# (4) aggregate_counts: distinct doc_ids for papers
# ---------------------------------------------------------------------------
def test_aggregate_counts_distinct_papers() -> None:
    counts = aggregate_counts(_state())
    # 3 evidence rows but only 2 distinct doc_ids (doc:p1 twice, doc:p2 once).
    assert counts["papers"] == 2
    assert counts["experiments"] == 3


def test_aggregate_counts_ignores_none_doc_ids() -> None:
    state = {
        "evidence": [
            {"doc_id": "doc:p1"},
            {"doc_id": None},
            {"evidence_id": "ev:x"},
        ],
    }
    # only the single real doc_id counts; None / missing doc_id are dropped.
    assert aggregate_counts(state)["papers"] == 1


# ---------------------------------------------------------------------------
# (5) no_baseline counts only 'missing_baseline' gaps
# ---------------------------------------------------------------------------
def test_aggregate_counts_no_baseline_only_missing_baseline() -> None:
    state = {
        "gaps": [
            {"type": "missing_baseline"},
            {"type": "missing_property"},
            {"type": "missing_baseline"},
            {"type": "contradiction"},
        ],
    }
    assert aggregate_counts(state)["no_baseline"] == 2


# ---------------------------------------------------------------------------
# (6) empty state → all counts zero, all tabs present
# ---------------------------------------------------------------------------
def test_empty_state_zero_counts_and_tabs_present() -> None:
    counts = aggregate_counts({})
    assert counts == {"experiments": 0, "papers": 0, "no_baseline": 0}
    tabs = build_tabs({}).as_dict()
    assert set(tabs) == _TAB_KEYS
    assert tabs["summary"]["counts"] == {"experiments": 0, "papers": 0, "no_baseline": 0}
    assert tabs["experiments"] == {"rows": [], "count": 0}
    assert tabs["graph"] == {"payload": None}


# ---------------------------------------------------------------------------
# (7) experiments tab row count == len(retrieved_experiments)
# ---------------------------------------------------------------------------
def test_experiments_tab_row_count_matches_state() -> None:
    state = _state()
    tabs = build_tabs(state).as_dict()
    n = len(state["retrieved_experiments"])  # type: ignore[arg-type]
    assert tabs["experiments"]["count"] == n
    assert len(tabs["experiments"]["rows"]) == n
    assert n == 3


# ---------------------------------------------------------------------------
# tab payload wiring + dataclass invariants
# ---------------------------------------------------------------------------
def test_tabs_carry_their_state_fields() -> None:
    tabs = build_tabs(_state()).as_dict()
    assert tabs["evidence"]["count"] == 3
    assert tabs["gaps"]["count"] == 2
    assert tabs["contradictions"]["items"] == [{"claimA": "c1", "claimB": "c2"}]
    assert tabs["graph"]["payload"] == {"nodes": [], "edges": []}
    assert tabs["summary"]["counts"]["papers"] == 2


def test_answer_tabs_frozen() -> None:
    tabs = AnswerTabs(
        summary={},
        experiments={},
        evidence={},
        graph={},
        gaps={},
        contradictions={},
    )
    assert set(tabs.as_dict()) == _TAB_KEYS
    with pytest.raises(AttributeError):
        tabs.summary = {"x": 1}  # type: ignore[misc]
