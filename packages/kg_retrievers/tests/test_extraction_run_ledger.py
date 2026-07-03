"""Tests for the per-extraction-run coverage + provenance ledger (§25.5/§25.3)."""

from __future__ import annotations

from kg_retrievers.extraction_run_ledger import (
    RunLedger,
    RunLedgerRow,
    build_run_ledger,
)


def _row(ledger: RunLedger, run_id: str) -> RunLedgerRow:
    """Return the single row for ``run_id`` (fails loudly if absent/duplicated)."""
    matches = [r for r in ledger.rows if r.run_id == run_id]
    assert len(matches) == 1, f"expected exactly one row for {run_id!r}, got {matches!r}"
    return matches[0]


def test_yield_ratio_seen10_emitted4_is_0_4() -> None:
    ledger = build_run_ledger(
        [{"extraction_run_id": "r1", "seen_segments": 10, "emitted_facts": 4}],
        [],
    )
    row = _row(ledger, "r1")
    assert row.seen_segments == 10
    assert row.emitted_facts == 4
    assert row.yield_ratio == 0.4


def test_observations_split_active_vs_retracted() -> None:
    ledger = build_run_ledger(
        [{"extraction_run_id": "r1", "seen_segments": 10, "emitted_facts": 4}],
        [
            {"extraction_run_id": "r1", "retracted": False},
            {"extraction_run_id": "r1"},
            {"extraction_run_id": "r1", "retracted": True},
        ],
    )
    row = _row(ledger, "r1")
    assert row.n_observations == 3
    assert row.n_active == 2
    assert row.n_retracted == 1


def test_run_only_in_observations_has_zero_seen_and_yield() -> None:
    ledger = build_run_ledger(
        [{"extraction_run_id": "r1", "seen_segments": 10, "emitted_facts": 4}],
        [{"extraction_run_id": "r2", "retracted": False}],
    )
    row = _row(ledger, "r2")
    assert row.seen_segments == 0
    assert row.emitted_facts == 0
    assert row.yield_ratio == 0.0
    assert row.n_observations == 1
    assert row.n_active == 1


def test_total_seen_sums_across_runs() -> None:
    ledger = build_run_ledger(
        [
            {"extraction_run_id": "r1", "seen_segments": 10, "emitted_facts": 4},
            {"extraction_run_id": "r2", "seen_segments": 5, "emitted_facts": 5},
        ],
        [],
    )
    assert ledger.total_seen == 15
    assert ledger.total_emitted == 9


def test_rows_sorted_by_run_id() -> None:
    ledger = build_run_ledger(
        [
            {"extraction_run_id": "r3", "seen_segments": 1, "emitted_facts": 1},
            {"extraction_run_id": "r1", "seen_segments": 1, "emitted_facts": 1},
            {"extraction_run_id": "r2", "seen_segments": 1, "emitted_facts": 1},
        ],
        [],
    )
    assert [r.run_id for r in ledger.rows] == ["r1", "r2", "r3"]


def test_seen_zero_emitted_zero_yields_zero() -> None:
    ledger = build_run_ledger(
        [{"extraction_run_id": "r1", "seen_segments": 0, "emitted_facts": 0}],
        [],
    )
    row = _row(ledger, "r1")
    assert row.yield_ratio == 0.0


def test_seen_segments_summed_within_a_run() -> None:
    ledger = build_run_ledger(
        [
            {"extraction_run_id": "r1", "seen_segments": 6, "emitted_facts": 2},
            {"extraction_run_id": "r1", "seen_segments": 4, "emitted_facts": 2},
        ],
        [],
    )
    row = _row(ledger, "r1")
    assert row.seen_segments == 10
    assert row.emitted_facts == 4
    assert row.yield_ratio == 0.4


def test_total_retracted_sums_across_runs() -> None:
    ledger = build_run_ledger(
        [
            {"extraction_run_id": "r1", "seen_segments": 2, "emitted_facts": 1},
            {"extraction_run_id": "r2", "seen_segments": 2, "emitted_facts": 1},
        ],
        [
            {"extraction_run_id": "r1", "retracted": True},
            {"extraction_run_id": "r2", "retracted": True},
            {"extraction_run_id": "r2", "retracted": True},
        ],
    )
    assert ledger.total_retracted == 3


def test_custom_run_key() -> None:
    ledger = build_run_ledger(
        [{"job": "j1", "seen_segments": 4, "emitted_facts": 2}],
        [{"job": "j1", "retracted": True}],
        run_key="job",
    )
    row = _row(ledger, "j1")
    assert row.yield_ratio == 0.5
    assert row.n_retracted == 1


def test_as_dict_rows_is_a_list_of_dicts() -> None:
    ledger = build_run_ledger(
        [{"extraction_run_id": "r1", "seen_segments": 10, "emitted_facts": 4}],
        [{"extraction_run_id": "r1", "retracted": True}],
    )
    d = ledger.as_dict()
    assert isinstance(d["rows"], list)
    assert all(isinstance(r, dict) for r in d["rows"])
    assert d["rows"][0]["yield_ratio"] == 0.4
    assert d["rows"][0]["n_retracted"] == 1
    assert d["total_seen"] == 10
    assert d["total_emitted"] == 4
    assert d["total_retracted"] == 1
