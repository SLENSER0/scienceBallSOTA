"""Absence triage action board — hand-checked over plain cell dicts (§25.11/§25.13).

The unit under test is store-free: it plans over already-classified absence cells
(``status``/``verdict`` dicts), so the fixtures below are hand-built and every expected
count/order is verifiable by eye.

Batch used by the grouping tests (8 cells):

    2× CONFIDENT_ABSENCE  → INVESTIGATE
    3× POSSIBLE_ABSENCE   → EXTRACT_MORE
    1× RETRACTED          → REVIEW_RETRACTION
    1× COVERED            → SKIP
    1× UNKNOWN            → SKIP

Hand-checked bucket counts: INVESTIGATE=2, EXTRACT_MORE=3, REVIEW_RETRACTION=1, SKIP=2.
With top_n=5 the shortlist is [inv0, inv1, ext0, ext1, ext2] — INVESTIGATE before
EXTRACT_MORE, capped at 5.
"""

from __future__ import annotations

from kg_retrievers.absence_triage import (
    ACTIONS,
    EXTRACT_MORE,
    INVESTIGATE,
    REVIEW_RETRACTION,
    SKIP,
    TriageBoard,
    TriageBucket,
    bucket_for,
    triage_absence,
)


def _cell(name: str, status: str, **extra: object) -> dict:
    """One absence cell dict — a diagnosis plus an identifying ``cell`` label."""
    return {"cell": name, "status": status, **extra}


def _batch() -> list[dict]:
    """The 8-cell hand-checked batch described in the module docstring."""
    return [
        _cell("inv0", "CONFIDENT_ABSENCE"),
        _cell("cov0", "COVERED"),
        _cell("inv1", "CONFIDENT_ABSENCE"),
        _cell("ext0", "POSSIBLE_ABSENCE"),
        _cell("ret0", "RETRACTED"),
        _cell("ext1", "POSSIBLE_ABSENCE"),
        _cell("unk0", "UNKNOWN"),
        _cell("ext2", "POSSIBLE_ABSENCE"),
    ]


# -- bucket_for: per-status mapping (assertions 1–4) -----------------------


def test_confident_absence_maps_to_investigate() -> None:
    assert bucket_for(_cell("x", "CONFIDENT_ABSENCE")) == INVESTIGATE


def test_possible_absence_maps_to_extract_more() -> None:
    assert bucket_for(_cell("x", "POSSIBLE_ABSENCE")) == EXTRACT_MORE


def test_covered_maps_to_skip() -> None:
    assert bucket_for(_cell("x", "COVERED")) == SKIP


def test_retracted_status_maps_to_review_retraction() -> None:
    assert bucket_for({"cell": "x", "status": "RETRACTED"}) == REVIEW_RETRACTION


def test_unknown_maps_to_skip() -> None:
    assert bucket_for(_cell("x", "UNKNOWN")) == SKIP


def test_verdict_key_and_lowercase_are_honoured() -> None:
    # Source constants are lowercase strings; ``verdict`` is the alternate key.
    assert bucket_for({"cell": "x", "verdict": "retracted"}) == REVIEW_RETRACTION
    assert bucket_for({"cell": "x", "verdict": "confident_absence"}) == INVESTIGATE


def test_unrecognised_or_missing_status_is_skip() -> None:
    assert bucket_for({"cell": "x"}) == SKIP
    assert bucket_for(_cell("x", "present")) == SKIP


# -- triage_absence: board shape + counts (assertion 5) --------------------


def test_board_bucket_counts_match_batch() -> None:
    board = triage_absence(_batch())
    assert isinstance(board, TriageBoard)
    # Every action always present, even when empty (stable board shape).
    assert set(board.buckets) == set(ACTIONS)
    for action, bucket in board.buckets.items():
        assert isinstance(bucket, TriageBucket)
        assert bucket.action == action
        assert bucket.count == len(bucket.items)
    # Assertion 5: INVESTIGATE count == number of confident-absence cells (2).
    n_confident = sum(1 for c in _batch() if c["status"] == "CONFIDENT_ABSENCE")
    assert board.buckets[INVESTIGATE].count == n_confident == 2
    assert board.buckets[EXTRACT_MORE].count == 3
    assert board.buckets[REVIEW_RETRACTION].count == 1
    assert board.buckets[SKIP].count == 2  # COVERED + UNKNOWN


# -- triage_absence: recommended_next ordering + cap (assertion 6) ---------


def test_recommended_next_investigate_precedes_extract_more_and_caps() -> None:
    board = triage_absence(_batch(), top_n=5)
    rec = board.recommended_next
    # Assertion 6: capped at top_n and INVESTIGATE items precede EXTRACT_MORE.
    assert len(rec) <= 5
    labels = [c["cell"] for c in rec]
    assert labels == ["inv0", "inv1", "ext0", "ext1", "ext2"]
    actions = [bucket_for(c) for c in rec]
    last_investigate = max(i for i, a in enumerate(actions) if a == INVESTIGATE)
    first_extract = min(i for i, a in enumerate(actions) if a == EXTRACT_MORE)
    assert last_investigate < first_extract


def test_recommended_next_truncates_to_top_n() -> None:
    board = triage_absence(_batch(), top_n=3)
    assert len(board.recommended_next) == 3
    # INVESTIGATE (2) then the first EXTRACT_MORE — never a SKIP/RETRACTION cell.
    assert [c["cell"] for c in board.recommended_next] == ["inv0", "inv1", "ext0"]


# -- empty input (assertion 7) ---------------------------------------------


def test_empty_input_zero_buckets_and_empty_shortlist() -> None:
    board = triage_absence([])
    assert set(board.buckets) == set(ACTIONS)
    assert all(bucket.count == 0 for bucket in board.buckets.values())
    assert all(bucket.items == [] for bucket in board.buckets.values())
    assert board.recommended_next == []


# -- as_dict round-trips ---------------------------------------------------


def test_as_dict_serialisation() -> None:
    board = triage_absence(_batch(), top_n=2)
    d = board.as_dict()
    assert set(d["buckets"]) == set(ACTIONS)
    assert d["buckets"][INVESTIGATE]["count"] == 2
    assert d["buckets"][INVESTIGATE]["action"] == INVESTIGATE
    assert [c["cell"] for c in d["recommended_next"]] == ["inv0", "inv1"]

    bucket_dict = board.buckets[EXTRACT_MORE].as_dict()
    assert bucket_dict == {
        "action": EXTRACT_MORE,
        "count": 3,
        "items": board.buckets[EXTRACT_MORE].items,
    }
