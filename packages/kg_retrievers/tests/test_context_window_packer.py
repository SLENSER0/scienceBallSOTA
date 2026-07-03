"""Tests for §12.11 context-window token-budget packing (hand-checkable)."""

from __future__ import annotations

from kg_retrievers.context_window_packer import PackResult, pack


def _hit(id_: str, score: float, tokens: int) -> dict:
    return {"id": id_, "score": score, "token_count": tokens}


def test_all_hits_fit_selected_in_score_order() -> None:
    hits = [_hit("a", 0.2, 10), _hit("b", 0.9, 10), _hit("c", 0.5, 10)]
    res = pack(hits, budget=100)
    # All fit; order is score-desc: b (0.9), c (0.5), a (0.2).
    assert res.selected_ids == ("b", "c", "a")
    assert res.used_tokens == 30
    assert res.dropped_ids == ()


def test_budget_zero_selects_nothing_all_dropped() -> None:
    hits = [_hit("a", 0.9, 5), _hit("b", 0.1, 5)]
    res = pack(hits, budget=0)
    assert res.selected_ids == ()
    assert res.used_tokens == 0
    # dropped_ids preserves input order.
    assert res.dropped_ids == ("a", "b")


def test_highest_score_picked_first() -> None:
    hits = [_hit("lo", 0.1, 3), _hit("hi", 0.99, 3), _hit("mid", 0.5, 3)]
    res = pack(hits, budget=100)
    assert res.selected_ids[0] == "hi"


def test_oversized_high_score_skipped_smaller_lower_selected() -> None:
    # 'big' has the top score but exceeds budget; 'small' (lower score) fits.
    hits = [_hit("big", 0.99, 50), _hit("small", 0.10, 5)]
    res = pack(hits, budget=10)
    # continue-not-break: skip 'big', still select 'small'.
    assert res.selected_ids == ("small",)
    assert res.used_tokens == 5
    assert res.dropped_ids == ("big",)


def test_used_tokens_never_exceeds_budget() -> None:
    hits = [_hit(str(i), 1.0 - i * 0.01, 7) for i in range(20)]
    res = pack(hits, budget=30)
    # 4 * 7 = 28 <= 30; a 5th would be 35 > 30.
    assert res.used_tokens == 28
    assert res.used_tokens <= res.budget
    assert len(res.selected_ids) == 4


def test_dropped_is_exact_complement_of_selected() -> None:
    hits = [_hit("a", 0.9, 6), _hit("b", 0.8, 6), _hit("c", 0.7, 6)]
    res = pack(hits, budget=10)
    # Only 'a' fits (6); adding 'b' would be 12 > 10; 'c' would be 12 > 10.
    assert res.selected_ids == ("a",)
    selected = set(res.selected_ids)
    dropped = set(res.dropped_ids)
    all_ids = {h["id"] for h in hits}
    assert selected.isdisjoint(dropped)
    assert selected | dropped == all_ids


def test_equal_scores_keep_input_order() -> None:
    hits = [_hit("x", 0.5, 4), _hit("y", 0.5, 4), _hit("z", 0.5, 4)]
    res = pack(hits, budget=100)
    assert res.selected_ids == ("x", "y", "z")


def test_as_dict_exposes_expected_keys() -> None:
    hits = [_hit("a", 0.9, 5), _hit("b", 0.1, 99)]
    res = pack(hits, budget=10)
    d = res.as_dict()
    assert set(d.keys()) == {"selected_ids", "used_tokens", "dropped_ids", "budget"}
    assert d["selected_ids"] == ("a",)
    assert d["used_tokens"] == 5
    assert d["dropped_ids"] == ("b",)
    assert d["budget"] == 10


def test_pack_result_is_frozen() -> None:
    res = pack([_hit("a", 0.5, 1)], budget=10)
    assert isinstance(res, PackResult)
    try:
        res.budget = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("PackResult must be frozen")


def test_custom_keys_supported() -> None:
    hits = [
        {"id": "a", "rank": 0.9, "toks": 4},
        {"id": "b", "rank": 0.8, "toks": 8},
    ]
    res = pack(hits, budget=5, token_key="toks", score_key="rank")
    assert res.selected_ids == ("a",)
    assert res.used_tokens == 4
    assert res.dropped_ids == ("b",)


def test_missing_score_defaults_to_zero() -> None:
    hits = [{"id": "a", "token_count": 3}, _hit("b", 0.5, 3)]
    res = pack(hits, budget=100)
    # 'b' (score 0.5) ranks above 'a' (missing -> 0.0).
    assert res.selected_ids == ("b", "a")


def test_empty_hits_returns_empty() -> None:
    res = pack([], budget=100)
    assert res.selected_ids == ()
    assert res.dropped_ids == ()
    assert res.used_tokens == 0
    assert res.budget == 100
