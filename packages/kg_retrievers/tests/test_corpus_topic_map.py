"""Tests for the numpy topic-map compute (spherical K-Means + PCA-3D + labels)."""

from __future__ import annotations

import json

import numpy as np

from kg_retrievers.corpus_topic_map import build_topic_map


def test_two_blobs_two_clusters() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.05, (80, 16)).astype(np.float32) + np.eye(1, 16, 0, dtype=np.float32)
    b = rng.normal(0, 0.05, (80, 16)).astype(np.float32) + np.eye(1, 16, 1, dtype=np.float32)
    x = np.vstack([a, b])
    texts = ["флотация реагент коллектор"] * 80 + ["температура плавка режим"] * 80
    out = build_topic_map(x, texts, k=2)
    assert out["total"] == 160
    assert out["k"] == 2
    assert len(out["clusters"]) == 2
    assert out["var3d"] > 0
    assert set(out["points"][0]) == {"x", "y", "z", "c", "t"}
    assert all(-1.31 <= p["x"] <= 1.31 for p in out["points"])
    json.dumps(out, ensure_ascii=False)  # JSON-serialisable


def test_empty_input() -> None:
    out = build_topic_map(np.zeros((0, 16), dtype=np.float32), [], k=8)
    assert out == {"points": [], "clusters": [], "total": 0, "shown": 0, "var3d": 0.0, "k": 0}


def test_k_clamped_when_fewer_points_than_k() -> None:
    x = np.eye(3, 16, dtype=np.float32)
    out = build_topic_map(x, ["a", "b", "c"], k=12)
    assert out["k"] == 3


def test_degenerate_duplicates_do_not_crash() -> None:
    # 25 rows but only 5 distinct → k-means++ weighting hits 0/0 without the guard.
    x = np.tile(np.eye(5, 16, dtype=np.float32), (5, 1))
    out = build_topic_map(x, ["x"] * 25, k=12)
    assert out["total"] == 25  # no ValueError('Probabilities contain NaN')


def test_nonfinite_rows_are_filtered() -> None:
    x = np.ones((40, 16), dtype=np.float32)
    x[3] = np.nan
    x[7] = np.inf
    out = build_topic_map(x, ["y"] * 40, k=4)
    assert out["total"] == 38  # two bad rows dropped, build succeeds


def test_deterministic_for_fixed_seed() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, (120, 16)).astype(np.float32)
    t = ["слово текст термин"] * 120
    a = build_topic_map(x, t, k=6)
    b = build_topic_map(x, t, k=6)
    assert [p["c"] for p in a["points"]] == [p["c"] for p in b["points"]]
    assert [p["x"] for p in a["points"]] == [p["x"] for p in b["points"]]
