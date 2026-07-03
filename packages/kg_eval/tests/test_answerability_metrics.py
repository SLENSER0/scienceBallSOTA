"""No-data answerability scoring tests (§25.15)."""

from __future__ import annotations

from kg_eval.answerability_metrics import AnswerabilityScores, score_answerability


def _rec(verdict: str, gold_no_data: bool, intent: str = "fact_lookup") -> dict:
    return {
        "predicted_verdict": verdict,
        "gold_no_data": gold_no_data,
        "intent": intent,
    }


def test_no_data_recall_both_flagged() -> None:
    # (1) two gold_no_data records, both flagged → recall 1.0
    recs = [
        _rec("genuine_gap", True),
        _rec("possible_miss", True),
    ]
    s = score_answerability(recs)
    assert s.no_data_recall == 1.0
    assert s.n_evaluated == 2


def test_no_data_recall_half() -> None:
    # (2) one of two gold_no_data flagged → recall 0.5
    recs = [
        _rec("genuine_gap", True),
        _rec("present", True),  # missed no-data
    ]
    s = score_answerability(recs)
    assert s.no_data_recall == 0.5


def test_false_gap_rate_quarter() -> None:
    # (3) one gold-has-data predicted genuine_gap over 4 data records → 0.25
    recs = [
        _rec("genuine_gap", False),
        _rec("present", False),
        _rec("present", False),
        _rec("abstain", False),
    ]
    s = score_answerability(recs)
    assert s.false_gap_rate == 0.25
    assert s.support["data_bearing"] == 4


def test_competence_search_excluded() -> None:
    # (4) competence_search record dropped → n_evaluated drops by 1
    recs = [
        _rec("present", False),
        _rec("genuine_gap", True, intent="competence_search"),
    ]
    with_drop = score_answerability(recs, data_bearing_only=True)
    without_drop = score_answerability(recs, data_bearing_only=False)
    assert with_drop.n_evaluated == 1
    assert without_drop.n_evaluated == 2
    # dropped record was the only gold_no_data → recall collapses to 0.0
    assert with_drop.no_data_recall == 0.0
    assert without_drop.no_data_recall == 1.0


def test_no_data_precision_half() -> None:
    # (5) two flagged, of which one is truly no-data → precision 0.5
    recs = [
        _rec("genuine_gap", True),  # flagged + no-data
        _rec("possible_miss", False),  # flagged but has data
    ]
    s = score_answerability(recs)
    assert s.no_data_precision == 0.5
    assert s.support["flagged"] == 2


def test_empty_records_all_zero() -> None:
    # (6) empty input → all metrics 0.0, n_evaluated 0
    s = score_answerability([])
    assert s == AnswerabilityScores(0.0, 0.0, 0.0, 0.0, 0, s.support)
    assert s.no_data_recall == 0.0
    assert s.no_data_precision == 0.0
    assert s.false_gap_rate == 0.0
    assert s.no_data_genuine_gap_rate == 0.0
    assert s.n_evaluated == 0
    assert s.support == {"gold_no_data": 0, "data_bearing": 0, "flagged": 0}


def test_genuine_gap_rate_possible_miss_only_zero() -> None:
    # (7) no-data set flagged only via possible_miss → genuine_gap_rate 0.0
    recs = [
        _rec("possible_miss", True),
        _rec("possible_miss", True),
    ]
    s = score_answerability(recs)
    d = s.as_dict()
    assert d["no_data_genuine_gap_rate"] == 0.0
    # yet still flagged → recall stays 1.0
    assert d["no_data_recall"] == 1.0


def test_support_counts() -> None:
    # (8) support dict tallies gold_no_data and data-bearing totals
    recs = [
        _rec("genuine_gap", True),
        _rec("present", True),
        _rec("present", False),
        _rec("possible_miss", False),
    ]
    s = score_answerability(recs)
    assert s.support["gold_no_data"] == 2
    assert s.support["data_bearing"] == 2
    assert s.support["flagged"] == 2  # genuine_gap + possible_miss
    # rounding is applied by as_dict
    assert s.as_dict()["support"] == {
        "gold_no_data": 2,
        "data_bearing": 2,
        "flagged": 2,
    }


def test_as_dict_rounds_floats() -> None:
    # one flagged of three gold_no_data → recall = 1/3 rounds to 0.3333
    recs = [
        _rec("genuine_gap", True),
        _rec("present", True),
        _rec("retracted", True),
    ]
    d = score_answerability(recs).as_dict()
    assert d["no_data_recall"] == 0.3333
    assert d["no_data_genuine_gap_rate"] == 0.3333
