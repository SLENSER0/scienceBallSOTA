"""[DE] Track-C absence-classification benchmark (§33.4/§33.5, D6).

The benchmark turns possible_miss-vs-genuine_gap into a measurable classification.
The load-bearing claims: (1) the current absence layer exposes its weakness on the
synthetic set — it flags genuine gaps as possible misses (false_possible_miss_rate
> 0); (2) the value methods measurably fix it — the ground-truth oracle and the
real production gate reach macro-F1 ≈ 1.0 with false_possible_miss_rate = 0, while
the offline D1 regex is a strong-but-imperfect approximation.
"""

from __future__ import annotations

import functools

from kg_eval.absence_eval import (
    BASELINES,
    business_metrics,
    confusion_matrix,
    macro_f1,
    per_class_prf,
    run,
)


@functools.lru_cache(maxsize=1)
def _payload() -> dict:
    return run(n_materials=12, seed=20260701)


def test_baseline_layer_exposes_the_weakness() -> None:
    p = _payload()
    ac = p["methods"]["absence_confidence"]
    b = ac["business"]
    # the exposed weakness: every genuine_gap cell is called a possible_miss.
    assert b["false_possible_miss_rate"] == 1.0
    assert b["miss_detection_recall"] == 1.0  # real misses are still caught
    assert b["no_data_recall"] == 0.0  # ...at the cost of never confirming a gap
    # the confusion matrix shows genuine_gap reality bleeding into possible_miss.
    cm = ac["confusion_matrix"]
    assert cm["genuine_gap"]["possible_miss"] == 20
    assert cm["genuine_gap"]["genuine_gap"] == 0


def test_value_methods_measurably_fix_it() -> None:
    p = _payload()
    oracle = p["methods"]["absence_confidence_value_oracle"]
    gate = p["methods"]["absence_confidence_value_gate"]
    regex = p["methods"]["absence_confidence_value_regex"]
    base_f1 = p["methods"]["absence_confidence"]["macro_f1"]

    # oracle = the achievable ceiling; the real production gate matches it because
    # value_present is written on the graph for every prose mention.
    for m in (oracle, gate):
        assert m["macro_f1"] == 1.0
        assert m["business"]["false_possible_miss_rate"] == 0.0
        assert m["business"]["accuracy"] == 1.0
    # the offline regex is a strong approximation: it fixes FALSE_MISS (named-no-
    # value in prose) but not ABSENT (no prose to read), so it lands in between.
    assert base_f1 < regex["macro_f1"] < 1.0
    assert regex["business"]["false_possible_miss_rate"] == 0.5


def test_value_signal_detector_is_accurate() -> None:
    # the D1 regex separates value-stated (TRUE_MISS) from named-only (FALSE_MISS)
    # perfectly on the constructed prose.
    vs = _payload()["value_signal"]
    assert vs["precision"] == 1.0 and vs["recall"] == 1.0 and vs["f1"] == 1.0
    assert vs["n"] == 22  # 12 TRUE_MISS + 10 FALSE_MISS


def test_baseline_ladder_is_a_clean_ablation() -> None:
    p = _payload()
    # naive_graph cannot emit possible_miss at all → never detects a real miss.
    assert p["methods"]["naive_graph"]["business"]["miss_detection_recall"] == 0.0
    # mentions_heuristic flips: catches every miss but over-flags every gap.
    assert p["methods"]["mentions_heuristic"]["business"]["miss_detection_recall"] == 1.0
    assert p["methods"]["mentions_heuristic"]["business"]["false_possible_miss_rate"] == 1.0
    assert set(BASELINES) == {"naive_graph", "mentions_heuristic", "static_modality"}


def test_abstain_and_covered_never_scored_correct() -> None:
    # unit-level guard on the metric helpers with a hand-built prediction set.
    from kg_eval.schemas import AbsencePrediction, DatasetManifest

    preds = [
        AbsencePrediction("m", "p", "x", "abstain", 0.5, 0.5, "genuine_gap"),
        AbsencePrediction("m", "q", "x", "covered", 0.0, 0.0, "present"),
        AbsencePrediction("m", "r", "x", "genuine_gap", 0.1, 0.9, "genuine_gap"),
    ]
    manifest = DatasetManifest(name="t", seed=1, profile="offline")
    b = business_metrics(preds, manifest)
    assert b["accuracy"] == round(1 / 3, 4)  # only the exact match counts
    assert b["abstention_rate"] == round(1 / 3, 4)
    cm = confusion_matrix(preds)
    assert cm["genuine_gap"]["abstain"] == 1 and cm["present"]["covered"] == 1
    prf = per_class_prf(preds)
    assert macro_f1(prf) >= 0.0  # defined even with degenerate classes


def test_run_is_deterministic() -> None:
    a, b = run(n_materials=6), run(n_materials=6)
    # drop the per-prediction lists (order-stable anyway) and compare summaries
    assert a["dataset"] == b["dataset"]
    assert a["value_signal"] == b["value_signal"]
    for m in a["methods"]:
        assert a["methods"][m]["macro_f1"] == b["methods"][m]["macro_f1"]
        assert a["methods"][m]["business"] == b["methods"][m]["business"]
