"""Corpus topic map (§17.x): 3D projection + clustering of the chunk-embedding space.

The retrieval corpus lives as ``:Chunk`` vectors in the Qdrant ``kg_chunks`` collection.
This turns that high-dimensional embedding cloud into a browsable 3D **topic map**:
spherical K-Means over the L2-normalized vectors groups chunks into topic clusters,
a numpy PCA gives each chunk 3D display coordinates, and a distinctiveness-weighted
term score labels every cluster. Pure numpy — no scikit-learn/UMAP dependency — so it
runs anywhere the retrievers package does.

The heavy build (tens of thousands of vectors) is meant to be precomputed
(``scripts/precompute_cluster_map.py``) or lazily built once and cached; never on a
per-request hot path — see :mod:`api_gateway.routers.cluster_map`.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import numpy as np

from kg_common import get_logger

_log = get_logger("corpus_topic_map")

_TOKEN = re.compile(r"[a-zа-яё]{4,}")
_REPEAT = re.compile(r"(.)\1\1")  # 3+ identical chars = OCR artifact
# RU/EN function words + scientific-boilerplate stopwords for cluster labelling.
# Kept short: common words appear in every cluster, so they already score low on
# distinctiveness — this list mainly suppresses the boilerplate that would otherwise win.
_STOP_STR = (
    "и в во не что он на я с со как а то все она так его но да ты за бы по только его для мы их "
    "чем при это том эта эти был была быть были может могут это как что при также является "
    "рис табл рисунок таблица данные результаты работе метод методы процесс процесса результат "
    "используется помощью течение случае связи вида этом более между над под без про обр "
    "the and for are was with this that from have has can will not its their which such been "
    "more than into also etc"
)
_STOP = frozenset(_STOP_STR.split())


def _clean_tok(w: str) -> bool:
    if w in _STOP or _REPEAT.search(w) or len(set(w)) < 3:
        return False
    # OCR that doubles every glyph («ооббооггаа…»)
    dbl = sum(w[i] == w[i + 1] for i in range(len(w) - 1))
    return not (len(w) >= 4 and dbl / (len(w) - 1) > 0.4)


def _toks(s: str) -> list[str]:
    return [w for w in _TOKEN.findall((s or "").lower()) if _clean_tok(w)]


def _kmeans(emb: np.ndarray, k: int, iters: int, seed: int) -> np.ndarray:
    """Spherical K-Means (cosine) on L2-normalized rows → per-row cluster labels."""
    rng = np.random.default_rng(seed)
    n = emb.shape[0]
    centers = np.empty((k, emb.shape[1]), dtype=emb.dtype)
    centers[0] = emb[rng.integers(n)]
    d2 = ((emb - centers[0]) ** 2).sum(1)
    for i in range(1, k):  # k-means++ seeding
        p = d2 / d2.sum()
        centers[i] = emb[rng.choice(n, p=p)]
        d2 = np.minimum(d2, ((emb - centers[i]) ** 2).sum(1))
    labels = np.zeros(n, dtype=np.int32)
    for _ in range(iters):
        labels = (emb @ centers.T).argmax(1)
        for i in range(k):
            m = labels == i
            if m.any():
                c = emb[m].mean(0)
                centers[i] = c / (np.linalg.norm(c) + 1e-9)
    return labels


def build_topic_map(
    vectors: np.ndarray,
    texts: list[str],
    *,
    k: int = 12,
    display: int = 6500,
    iters: int = 30,
    seed: int = 7,
) -> dict[str, Any]:
    """Cluster + 3D-project the embedding cloud into a browsable topic-map payload.

    Returns ``{points:[{x,y,z,c,t}], clusters:[{id,label,terms,size,pct}], total,
    shown, var3d, k}`` — a compact, JSON-serialisable blob. Coordinates are scaled to
    a symmetric cube for the viewer; ``c`` is the cluster id, ``t`` a short hover text.
    """
    emb = np.asarray(vectors, dtype=np.float32)
    n = emb.shape[0]
    if n == 0:
        return {"points": [], "clusters": [], "total": 0, "shown": 0, "var3d": 0.0, "k": 0}
    k = max(2, min(k, n))
    emb /= np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9
    rng = np.random.default_rng(seed)

    labels = _kmeans(emb, k, iters, seed)
    sizes = np.bincount(labels, minlength=k)

    # PCA→3D via covariance eigendecomposition (fast: dim×dim, dim≈384)
    embc = emb - emb.mean(0)
    evals, evecs = np.linalg.eigh(embc.T @ embc)
    top3 = evecs[:, ::-1][:, :3]
    coords = embc @ top3
    scale = np.percentile(np.abs(coords), 99, axis=0) + 1e-9
    coords = np.clip(coords / scale, -1.3, 1.3)
    var3d = float(evals[::-1][:3].sum() / evals.sum() * 100.0)

    # distinctiveness-weighted term labels (presence per chunk, per cluster)
    cluster_tf = [Counter() for _ in range(k)]
    for i, t in enumerate(texts):
        cluster_tf[labels[i]].update(set(_toks(t)))
    global_df: Counter = Counter()
    for c in cluster_tf:
        global_df.update(c)

    def label_terms(ci: int) -> list[str]:
        scored = []
        for w, cnt in cluster_tf[ci].items():
            if cnt < 3:
                continue
            score = (cnt / global_df[w]) * math.log(1 + cnt)
            scored.append((score, w))
        scored.sort(reverse=True)
        return [w for _, w in scored[:5]]

    labels_terms = [label_terms(i) for i in range(k)]

    # stratified display sample so small clusters stay visible
    idx: list[np.ndarray] = []
    for i in range(k):
        ids = np.where(labels == i)[0]
        take = min(len(ids), max(120, int(display * len(ids) / n)))
        idx.append(rng.choice(ids, size=take, replace=False))
    sel = np.concatenate(idx)
    rng.shuffle(sel)

    points = [
        {
            "x": round(float(coords[i, 0]), 3),
            "y": round(float(coords[i, 1]), 3),
            "z": round(float(coords[i, 2]), 3),
            "c": int(labels[i]),
            "t": (texts[i] or "")[:140],
        }
        for i in sel
    ]
    clusters = [
        {
            "id": i,
            "label": " · ".join(labels_terms[i][:3]) or f"кластер {i}",
            "terms": labels_terms[i],
            "size": int(sizes[i]),
            "pct": round(100.0 * sizes[i] / n, 1),
        }
        for i in range(k)
    ]
    _log.info("corpus_topic_map.built", total=n, k=k, shown=len(points), var3d=round(var3d, 1))
    return {
        "points": points,
        "clusters": clusters,
        "total": n,
        "shown": len(points),
        "var3d": round(var3d, 1),
        "k": k,
    }


def fetch_and_build(*, k: int = 12, limit: int | None = None) -> dict[str, Any]:
    """Scroll all chunk vectors from Qdrant (server profile) and build the topic map.

    ``limit`` caps how many vectors are read (None = the whole collection). Returns the
    :func:`build_topic_map` payload; an empty payload if the vector store is unreachable.
    """
    try:
        from kg_retrievers.qdrant_server_store import QdrantServerStore

        qs = QdrantServerStore()
    except Exception as exc:
        _log.warning("corpus_topic_map.no_vector_store", error=str(exc)[:120])
        return {"points": [], "clusters": [], "total": 0, "shown": 0, "var3d": 0.0, "k": 0}

    vecs: list[list[float]] = []
    texts: list[str] = []
    offset = None
    while True:
        pts, offset = qs.client.scroll(
            qs.collection, limit=2000, offset=offset, with_vectors=True, with_payload=True
        )
        for p in pts:
            if not p.vector:
                continue
            vecs.append(p.vector)
            texts.append((p.payload.get("text") or "").replace("\n", " ").strip()[:180])
            if limit and len(vecs) >= limit:
                break
        if offset is None or (limit and len(vecs) >= limit):
            break
    return build_topic_map(np.asarray(vecs, dtype=np.float32), texts, k=k)
