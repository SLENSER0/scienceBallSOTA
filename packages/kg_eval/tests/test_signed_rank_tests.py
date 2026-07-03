"""Tests for nonparametric paired significance tests (§18.11).

Hand-checkable assertions on wilcoxon_signed_rank + sign_test + analyze. RU/EN.
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_eval.signed_rank_tests import (
    PairedTestResult,
    analyze,
    sign_test,
    wilcoxon_signed_rank,
)


def test_wilcoxon_simple_positive_ranks() -> None:
    """diffs 0.1, 0.0, 0.2 → нуль отброшен, ранги 1,2 → (W+, W-) == (3.0, 0.0)."""
    system = [0.5, 0.6, 0.7]
    baseline = [0.4, 0.6, 0.5]
    assert wilcoxon_signed_rank(system, baseline) == (3.0, 0.0)


def test_sign_test_two_up_zero_down() -> None:
    """Тот же вход: 2 вверх, 0 вниз, точный биномиальный p == 0.5."""
    system = [0.5, 0.6, 0.7]
    baseline = [0.4, 0.6, 0.5]
    assert sign_test(system, baseline) == (2, 0, 0.5)


def test_equal_inputs_no_nonzero() -> None:
    """Идентичные входы → n_nonzero == 0 и w_plus == 0.0."""
    scores = [0.4, 0.5, 0.6]
    res = analyze(scores, scores)
    assert res.n_nonzero == 0
    assert res.w_plus == 0.0
    assert res.w_minus == 0.0


def test_analyze_counts_nonzero_pairs() -> None:
    """analyze над примером из спеки → ровно 2 ненулевые пары."""
    res = analyze([0.5, 0.6, 0.7], [0.4, 0.6, 0.5])
    assert res.n_nonzero == 2


def test_wilcoxon_average_ranks_on_tie() -> None:
    """|d| = 1,1,2 → ранги 1.5,1.5,3, все положительные → w_plus == 6.0."""
    system = [1, 2, 4]
    baseline = [0, 1, 2]
    w_plus, w_minus = wilcoxon_signed_rank(system, baseline)
    assert w_plus == 6.0
    assert w_minus == 0.0


def test_length_mismatch_raises() -> None:
    """Несовпадающие длины → ValueError во всех точках входа."""
    with pytest.raises(ValueError):
        wilcoxon_signed_rank([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        sign_test([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        analyze([1.0, 2.0], [1.0])


def test_as_dict_sign_p_value() -> None:
    """as_dict()['sign_p_two_sided'] == 0.5 для примера 2 вверх / 0 вниз."""
    d = analyze([0.5, 0.6, 0.7], [0.4, 0.6, 0.5]).as_dict()
    assert d["sign_p_two_sided"] == 0.5


def test_statistic_is_min_of_rank_sums() -> None:
    """statistic == min(W+, W-); при спуске всех пар W+ == 0.0 → statistic 0.0."""
    res = analyze([0.1, 0.2, 0.3], [0.4, 0.5, 0.6])
    assert res.w_plus == 0.0
    assert res.w_minus == 6.0
    assert res.statistic == 0.0


def test_result_is_frozen() -> None:
    """PairedTestResult неизменяем (frozen)."""
    res = analyze([0.5, 0.6], [0.4, 0.5])
    assert isinstance(res, PairedTestResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.n = 99  # type: ignore[misc]


def test_symmetric_split_p_value_one() -> None:
    """Симметричный сплит 1 вверх / 1 вниз → двусторонний p == 1.0."""
    _, _, p = sign_test([1.0, 0.0], [0.0, 1.0])
    assert p == 1.0


def test_as_dict_has_all_fields() -> None:
    """as_dict() содержит все восемь полей результата."""
    d = analyze([0.5, 0.6, 0.7], [0.4, 0.6, 0.5]).as_dict()
    assert set(d) == {
        "n",
        "n_nonzero",
        "w_plus",
        "w_minus",
        "statistic",
        "sign_pos",
        "sign_neg",
        "sign_p_two_sided",
    }
