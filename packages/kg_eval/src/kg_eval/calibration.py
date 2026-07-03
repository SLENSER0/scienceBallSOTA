"""[DE] Probability calibration for the absence layer (spec §33, port of science_ball).

Pure-NumPy + stdlib, fully offline. Scores the emitted ``p_extractor_missed`` as a
binary forecast of the event "a measurable fact is present in source but was
missed" (true reality = ``possible_miss``). Scope: only the probabilistic cells —
true reality ∈ {``genuine_gap``, ``possible_miss``}; ``present`` / ``retracted``
emit p=0 by rule and are excluded. **Nothing is ever written back to production
thresholds** — the cost-based threshold study runs on a held-out split only.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

# cost[true_label][predicted_verdict]. A false genuine_gap on a true possible_miss
# (a wasted R&D lead) is the single most expensive error; abstain always costs 1.0.
COST_MATRIX: dict[str, dict[str, float]] = {
    "possible_miss": {
        "possible_miss": 0.0,
        "genuine_gap": 5.0,
        "present": 3.0,
        "abstain": 1.0,
        "retracted": 3.0,
    },
    "genuine_gap": {
        "possible_miss": 2.0,
        "genuine_gap": 0.0,
        "present": 3.0,
        "abstain": 1.0,
        "retracted": 3.0,
    },
    "present": {
        "possible_miss": 4.0,
        "genuine_gap": 4.0,
        "present": 0.0,
        "abstain": 1.0,
        "retracted": 4.0,
    },
    "retracted": {
        "possible_miss": 4.0,
        "genuine_gap": 4.0,
        "present": 4.0,
        "abstain": 1.0,
        "retracted": 0.0,
    },
}


def _clip(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(p, eps, 1.0 - eps)


def _nan_round(x: float, nd: int = 4) -> float | None:
    return None if x != x else round(x, nd)  # x != x is the NaN test


def brier_score(p: np.ndarray, y: np.ndarray) -> float:
    """Mean squared error: (1/N) Σ (pᵢ − yᵢ)²."""
    return float(np.mean((p - y) ** 2)) if len(p) else float("nan")


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    """Clipped binary cross-entropy (eps=1e-6)."""
    if not len(p):
        return float("nan")
    pc = _clip(p)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> tuple[float, list[dict[str, Any]]]:
    """Expected Calibration Error over equal-width bins + reliability diagram.

    ECE = Σ_b (n_b/N)·|conf_b − acc_b|. Bins are half-open ``[lo, hi)`` except the
    last, which is closed ``[lo, hi]`` so ``p == 1.0`` is included.
    """
    if not len(p):
        return float("nan"), []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = len(p)
    err = 0.0
    diagram: list[dict[str, Any]] = []
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        mask = (p >= lo) & (p <= hi if b == n_bins - 1 else p < hi)
        n = int(mask.sum())
        if n == 0:
            diagram.append(
                {"bin": [round(lo, 2), round(hi, 2)], "n": 0, "confidence": None, "accuracy": None}
            )
            continue
        conf = float(np.mean(p[mask]))
        acc = float(np.mean(y[mask]))
        err += (n / total) * abs(conf - acc)
        diagram.append(
            {
                "bin": [round(lo, 2), round(hi, 2)],
                "n": n,
                "confidence": round(conf, 3),
                "accuracy": round(acc, 3),
            }
        )
    return float(err), diagram


def _tie_average(p: np.ndarray, ranks: np.ndarray) -> None:
    """Replace tied-score ranks with their group mean (in place)."""
    order = np.argsort(p, kind="mergesort")
    sp = p[order]
    i = 0
    n = len(p)
    while i < n:
        j = i
        while j + 1 < n and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            avg = ranks[order[i : j + 1]].mean()
            ranks[order[i : j + 1]] = avg
        i = j + 1


def auroc(p: np.ndarray, y: np.ndarray) -> float:
    """AUC via the tie-averaged rank / Mann–Whitney U identity."""
    pos = y == 1
    neg = y == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")  # only one class present
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    _tie_average(p, ranks)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def auprc(p: np.ndarray, y: np.ndarray) -> float:
    """Average precision (area under PR), tie-grouped like sklearn."""
    if not len(p) or y.sum() == 0:
        return float("nan")
    order = np.argsort(-p, kind="mergesort")
    ps, ys = p[order], y[order]
    total_pos = float(ys.sum())
    tp = fp = 0.0
    ap = 0.0
    prev_r = 0.0
    i = 0
    n = len(ps)
    while i < n:
        j = i
        while j + 1 < n and ps[j + 1] == ps[i]:
            j += 1
        group = ys[i : j + 1]
        tp += float(group.sum())
        fp += (j + 1 - i) - float(group.sum())
        precision = tp / (tp + fp)
        recall = tp / total_pos
        ap += precision * (recall - prev_r)
        prev_r = recall
        i = j + 1
    return float(ap)


def probability_report(
    p_missed: list[float], is_miss: list[int], *, n_bins: int = 10
) -> dict[str, Any]:
    """Full probability-quality report for ``p_extractor_missed`` vs the miss event."""
    p = np.asarray(p_missed, dtype=float)
    y = np.asarray(is_miss, dtype=float)
    e, diagram = ece(p, y, n_bins=n_bins)
    return {
        "n": len(p),
        "n_positive": int(y.sum()),
        "base_rate": round(float(y.mean()), 4) if len(y) else None,
        "brier": _nan_round(brier_score(p, y)),
        "log_loss": _nan_round(log_loss(p, y)),
        "ece": _nan_round(e),
        "auroc": _nan_round(auroc(p, y)),
        "auprc": _nan_round(auprc(p, y)),
        "reliability_diagram": diagram,
        "scope": "cells with no active observation and no retraction "
        "(true ∈ {genuine_gap, possible_miss})",
    }


def bootstrap_ci(
    values: list[float],
    stat_fn: Any,
    *,
    n_boot: int = 1000,
    seed: int = 12345,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Percentile bootstrap CI for a scalar statistic (deterministic PCG64 seed)."""
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n == 0:
        return {"point": None, "lo": None, "hi": None, "n": 0, "warning": "empty sample"}
    rng = np.random.default_rng(seed)
    point = float(stat_fn(arr))
    boots = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        boots[i] = stat_fn(arr[rng.integers(0, n, n)])
    lo = float(np.percentile(boots, 100 * alpha / 2))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2)))
    out: dict[str, Any] = {"point": round(point, 4), "lo": round(lo, 4), "hi": round(hi, 4), "n": n}
    if n < 10:
        out["warning"] = f"n={n} < 10 — interval is wide; not a statistically strong claim"
    return out


# -- cost-based threshold study (held-out split; NEVER written back) -------
_GRID: tuple[float, ...] = (
    0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85,
)  # fmt: skip


def _verdict_from_thresholds(
    active: int,
    retracted: int,
    mentioned: bool,
    p_missed: float,
    possible_miss_at: float,
    genuine_gap_at: float,
) -> str:
    if active > 0:
        return "present"
    if retracted > 0:
        return "retracted"
    if not mentioned:
        return "genuine_gap"
    if p_missed >= possible_miss_at:
        return "possible_miss"
    if p_missed <= genuine_gap_at:
        return "genuine_gap"
    return "abstain"


def select_thresholds(
    cells: list[dict[str, Any]],
    *,
    calib_frac: float = 0.5,
    grid: tuple[float, ...] = _GRID,
    abstain_budget: float = 0.35,
) -> dict[str, Any]:
    """Grid-search threshold pairs minimising expected cost on a calibration split
    (leakage-free by stable hash), evaluated on a held-out test split. Never written
    back to production."""

    def fold(c: dict[str, Any]) -> str:
        h = int(hashlib.sha1(c["key"].encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        return "calib" if h < calib_frac else "test"

    calib = [c for c in cells if fold(c) == "calib"]
    test = [c for c in cells if fold(c) == "test"]

    def cost_of(
        rule_cells: list[dict[str, Any]], pm_at: float, gg_at: float
    ) -> tuple[float, float]:
        if not rule_cells:
            return float("inf"), 0.0
        total = 0.0
        abstains = 0
        for c in rule_cells:
            v = _verdict_from_thresholds(
                c["active"], c["retracted"], c["mentioned"], c["p_missed"], pm_at, gg_at
            )
            total += COST_MATRIX.get(c["true_label"], {}).get(v, 3.0)
            if v == "abstain":
                abstains += 1
        return total / len(rule_cells), abstains / len(rule_cells)

    def _search(with_budget: bool) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for gg in grid:
            for pm in grid:
                if pm < gg:
                    continue
                mean_cost, abst_rate = cost_of(calib, pm, gg)
                if with_budget and abst_rate > abstain_budget:
                    continue
                if best is None or mean_cost < best["calib_cost"]:
                    best = {
                        "possible_miss_at": pm,
                        "genuine_gap_at": gg,
                        "calib_cost": round(mean_cost, 4),
                        "calib_abstain_rate": round(abst_rate, 4),
                    }
        return best

    best = _search(with_budget=True)
    if best is None:
        best = _search(with_budget=False)
        if best is not None:
            best["note"] = "abstain budget could not be met; unconstrained minimum"

    sel_cost, sel_abst = (
        cost_of(test, best["possible_miss_at"], best["genuine_gap_at"])
        if best
        else (float("inf"), 0.0)
    )
    prod_cost, prod_abst = cost_of(test, 0.60, 0.25)
    return {
        "selected": best,
        "test_cost_selected": round(sel_cost, 4),
        "test_abstain_selected": round(sel_abst, 4),
        "test_cost_production_0.60_0.25": round(prod_cost, 4),
        "test_abstain_production": round(prod_abst, 4),
        "n_calib": len(calib),
        "n_test": len(test),
        "note": "Thresholds are evaluated on a held-out split and NOT written back to production.",
    }
