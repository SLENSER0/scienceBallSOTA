"""[DE] Probability calibration metrics (§33, D7).

Hand-checkable NumPy metric math on toy vectors, plus determinism of the bootstrap
CI and the leakage-free cost-based threshold study.
"""

from __future__ import annotations

import numpy as np

from kg_eval.calibration import (
    auprc,
    auroc,
    brier_score,
    ece,
    log_loss,
    probability_report,
    select_thresholds,
)
from kg_eval.calibration import bootstrap_ci as boot


def _a(x: list[float]) -> np.ndarray:
    return np.asarray(x, dtype=float)


def test_brier_and_log_loss() -> None:
    assert brier_score(_a([1.0, 0.0]), _a([1, 0])) == 0.0
    assert brier_score(_a([0.5, 0.5]), _a([1, 0])) == 0.25
    # perfect-confidence correct predictions → near-zero clipped log-loss
    assert log_loss(_a([1.0, 0.0]), _a([1, 0])) < 1e-4


def test_auroc_perfect_and_random() -> None:
    assert auroc(_a([0.9, 0.1]), _a([1, 0])) == 1.0  # perfect separation
    assert auroc(_a([0.1, 0.9]), _a([1, 0])) == 0.0  # perfectly wrong
    # ties across classes → 0.5 (uninformative)
    assert auroc(_a([0.5, 0.5]), _a([1, 0])) == 0.5
    # single class → nan
    assert auroc(_a([0.5, 0.6]), _a([1, 1])) != auroc(_a([0.5, 0.6]), _a([1, 1]))


def test_auprc_perfect() -> None:
    assert auprc(_a([0.9, 0.8, 0.1]), _a([1, 1, 0])) == 1.0
    assert auprc(_a([0.1, 0.2]), _a([0, 0])) != auprc(_a([0.1, 0.2]), _a([0, 0]))  # no pos → nan


def test_ece_perfectly_calibrated() -> None:
    # 10 items at p=0.0 all negative, 10 at p=1.0 all positive → ECE 0.
    p = _a([0.0] * 10 + [1.0] * 10)
    y = _a([0] * 10 + [1] * 10)
    e, diagram = ece(p, y, n_bins=10)
    assert abs(e) < 1e-9
    assert len(diagram) == 10


def test_probability_report_shape() -> None:
    rep = probability_report([0.7, 0.2, 0.9, 0.3], [1, 0, 1, 0])
    assert rep["n"] == 4 and rep["n_positive"] == 2
    assert set(rep) >= {
        "brier",
        "log_loss",
        "ece",
        "auroc",
        "auprc",
        "reliability_diagram",
        "scope",
    }
    # empty input → nan metrics serialise as None
    empty = probability_report([], [])
    assert empty["brier"] is None and empty["auroc"] is None


def test_bootstrap_ci_deterministic() -> None:
    vals = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0]
    a = boot(vals, np.mean)
    b = boot(vals, np.mean)
    assert a == b  # fixed PCG64 seed → identical interval
    assert a["lo"] <= a["point"] <= a["hi"]
    assert "warning" not in a  # n >= 10
    assert boot([1.0, 0.0], np.mean)["warning"].startswith("n=2")
    assert boot([], np.mean) == {
        "point": None,
        "lo": None,
        "hi": None,
        "n": 0,
        "warning": "empty sample",
    }


def test_threshold_study_is_leakage_free_and_not_written_back() -> None:
    cells = [
        {
            "key": f"m{i}|p",
            "true_label": "possible_miss" if i % 2 else "genuine_gap",
            "active": 0,
            "retracted": 0,
            "mentioned": True,
            "p_missed": 0.7 if i % 2 else 0.1,
        }
        for i in range(20)
    ]
    out = select_thresholds(cells)
    # split is content-hash based, deterministic, and disjoint.
    assert out["n_calib"] + out["n_test"] == 20
    assert select_thresholds(cells)["n_calib"] == out["n_calib"]
    assert "NOT written back to production" in out["note"]
    assert 0.0 <= out["selected"]["genuine_gap_at"] <= out["selected"]["possible_miss_at"] <= 1.0
