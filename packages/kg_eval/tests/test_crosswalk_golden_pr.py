"""Tests for the precision/recall crosswalk golden regression (§20.13)."""

from __future__ import annotations

from kg_eval.crosswalk_golden_pr import CrosswalkGoldenResult, evaluate_crosswalk


def _golden() -> dict[tuple[str, str], str]:
    return {
        ("elabftw", "a"): "c:1",
        ("openbis", "b"): "c:2",
    }


def test_identical_golden_and_predicted_perfect_scores() -> None:
    golden = _golden()
    res = evaluate_crosswalk(golden, dict(golden))
    assert res.total == 2
    assert res.correct == 2
    assert res.correct == res.total
    assert res.wrong == 0
    assert res.missing == 0
    assert res.precision == 1.0
    assert res.recall == 1.0
    assert res.mismatches == ()


def test_flipping_one_predicted_value_lowers_recall_and_records_mismatch() -> None:
    golden = _golden()
    pred = dict(golden)
    pred[("openbis", "b")] = "c:99"
    res = evaluate_crosswalk(golden, pred)
    assert res.recall < 1.0
    assert res.recall == 0.5
    assert res.correct == 1
    assert res.wrong == 1
    assert len(res.mismatches) == 1


def test_mismatch_entry_carries_expected_and_got_ids() -> None:
    golden = _golden()
    pred = dict(golden)
    pred[("openbis", "b")] = "c:99"
    res = evaluate_crosswalk(golden, pred)
    key, expected, got = res.mismatches[0]
    assert key == ("openbis", "b")
    assert expected == "c:2"
    assert got == "c:99"


def test_dropping_one_predicted_key_counts_as_missing() -> None:
    golden = _golden()
    pred = {("elabftw", "a"): "c:1"}
    res = evaluate_crosswalk(golden, pred)
    assert res.missing == 1
    assert res.correct == 1
    assert res.wrong == 0
    # recall reflects the single hit over two golden keys.
    assert res.recall == 0.5


def test_extra_predicted_key_lowers_precision_below_one() -> None:
    golden = _golden()
    pred = dict(golden)
    pred[("mp", "z")] = "c:7"  # not in golden
    res = evaluate_crosswalk(golden, pred)
    assert res.recall == 1.0
    assert res.precision < 1.0
    assert res.precision == 2 / 3


def test_empty_predicted_gives_zero_precision() -> None:
    golden = _golden()
    res = evaluate_crosswalk(golden, {})
    assert res.precision == 0.0
    assert res.recall == 0.0
    assert res.correct == 0
    assert res.missing == 2


def test_empty_golden_gives_zero_recall() -> None:
    res = evaluate_crosswalk({}, {("elabftw", "a"): "c:1"})
    assert res.recall == 0.0
    assert res.precision == 0.0
    assert res.total == 0
    assert res.correct == 0


def test_as_dict_contains_recall() -> None:
    golden = _golden()
    res = evaluate_crosswalk(golden, dict(golden))
    d = res.as_dict()
    assert "recall" in d
    assert d["recall"] == 1.0
    assert "precision" in d
    assert set(d) == {
        "total",
        "correct",
        "wrong",
        "missing",
        "precision",
        "recall",
        "mismatches",
    }


def test_result_is_frozen() -> None:
    res = CrosswalkGoldenResult(0, 0, 0, 0, 0.0, 0.0, ())
    try:
        res.total = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("CrosswalkGoldenResult must be frozen")
