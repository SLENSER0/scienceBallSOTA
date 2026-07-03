"""Verdict-aware absence confusion matrix (§25.11/§25.15)."""

from __future__ import annotations

from pytest import approx

from kg_eval.absence_verdict_confusion import (
    VERDICTS,
    VerdictConfusion,
    build_verdict_confusion,
)

# Hand-checked example from the §25.15 spec:
#   (genuine_gap, genuine_gap)   -> diagonal
#   (genuine_gap, abstain)       -> off-diagonal miss
#   (possible_miss, possible_miss) x2 -> diagonal
#   (retracted, retracted)       -> diagonal
# 4 of 5 pairs correct -> accuracy 0.8.
_PAIRS: list[tuple[str, str]] = [
    ("genuine_gap", "genuine_gap"),
    ("genuine_gap", "abstain"),
    ("possible_miss", "possible_miss"),
    ("possible_miss", "possible_miss"),
    ("retracted", "retracted"),
]


def test_verdicts_constant() -> None:
    assert VERDICTS == ("genuine_gap", "possible_miss", "retracted", "abstain")


def test_matrix_cells() -> None:
    vc = build_verdict_confusion(_PAIRS)
    assert vc.matrix["genuine_gap"]["abstain"] == 1
    assert vc.matrix["genuine_gap"]["genuine_gap"] == 1
    assert vc.matrix["possible_miss"]["possible_miss"] == 2
    assert vc.matrix["retracted"]["retracted"] == 1


def test_matrix_is_full_grid_of_verdicts() -> None:
    vc = build_verdict_confusion(_PAIRS)
    for gold in VERDICTS:
        assert set(vc.matrix[gold]) == set(VERDICTS)


def test_accuracy_and_support() -> None:
    vc = build_verdict_confusion(_PAIRS)
    assert vc.accuracy == 0.8  # 4 of 5 on the diagonal
    assert vc.support == 5


def test_per_verdict_recall_and_precision() -> None:
    vc = build_verdict_confusion(_PAIRS)
    # genuine_gap: 2 gold, 1 correct -> recall 1/2.
    assert vc.per_verdict["genuine_gap"]["recall"] == 0.5
    assert vc.per_verdict["genuine_gap"]["precision"] == 1.0  # 1 pred, 1 correct
    assert vc.per_verdict["genuine_gap"]["support"] == 2.0
    # possible_miss: 2 pred all correct -> precision 1.0, recall 1.0.
    assert vc.per_verdict["possible_miss"]["precision"] == 1.0
    assert vc.per_verdict["possible_miss"]["recall"] == 1.0
    assert vc.per_verdict["possible_miss"]["f1"] == 1.0


def test_genuine_gap_f1_is_harmonic_mean() -> None:
    vc = build_verdict_confusion(_PAIRS)
    # precision 1.0, recall 0.5 -> f1 = 2*1*0.5 / 1.5 = 2/3.
    assert vc.per_verdict["genuine_gap"]["f1"] == approx(2 / 3)


def test_unseen_verdict_has_zero_support_no_divide_by_zero() -> None:
    vc = build_verdict_confusion(_PAIRS)
    # 'abstain' is never a gold verdict here -> support 0, recall 0.0.
    abstain = vc.per_verdict["abstain"]
    assert abstain["support"] == 0.0
    assert abstain["recall"] == 0.0
    # It is predicted once (a wrong prediction) -> precision 0/1 = 0.0.
    assert abstain["precision"] == 0.0
    assert abstain["f1"] == 0.0
    # 'retracted' is never predicted wrongly and appears once correctly; a truly unseen
    # verdict would be one never present at all — confirm all four verdicts have a row.
    assert set(vc.per_verdict) == set(VERDICTS)


def test_empty_pairs_all_zero_no_divide_by_zero() -> None:
    vc = build_verdict_confusion([])
    assert vc.support == 0
    assert vc.accuracy == 0.0
    for v in VERDICTS:
        assert vc.per_verdict[v] == {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "support": 0.0,
        }


def test_as_dict_matrix_is_plain_nested_dict() -> None:
    vc = build_verdict_confusion(_PAIRS)
    d = vc.as_dict()
    matrix = d["matrix"]
    assert type(matrix) is dict
    assert type(matrix["genuine_gap"]) is dict
    assert matrix["genuine_gap"]["abstain"] == 1
    assert d["accuracy"] == 0.8
    assert d["support"] == 5


def test_frozen_dataclass_immutable() -> None:
    vc = build_verdict_confusion(_PAIRS)
    assert isinstance(vc, VerdictConfusion)
    try:
        vc.accuracy = 0.0  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("VerdictConfusion must be frozen")
