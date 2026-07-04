"""Corpus topic-map endpoint (§17.x): serve the 3D chunk-embedding cluster map.

``GET /api/v1/cluster-map`` returns a browsable projection of the retrieval corpus's
chunk-embedding space — spherical K-Means topic clusters + numpy PCA 3D coordinates +
term labels (see :func:`kg_retrievers.corpus_topic_map.build_topic_map`). The build is
heavy (tens of thousands of vectors) so it is **never** run on the hot path: the payload
is read from a durable ``var/cluster_map.json`` (written by
``scripts/precompute_cluster_map.py``) and held in a per-process cache invalidated by the
file's mtime. If the file is missing, the endpoint builds it once, persists it atomically,
and serves it — subsequent requests are instant. ``?refresh=true`` forces a rebuild.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from kg_common import get_logger, get_settings

router = APIRouter(prefix="/api/v1/cluster-map", tags=["cluster-map"])
_log = get_logger("cluster_map")

# Per-process cache: (mtime, payload). Invalidated when the durable file changes.
_cache: dict[str, Any] = {"mtime": None, "data": None}


def _path() -> Path:
    return Path(get_settings().runtime_dir) / "cluster_map.json"


def _load_file() -> dict | None:
    p = _path()
    if not p.exists():
        return None
    mt = p.stat().st_mtime
    if _cache["data"] is not None and _cache["mtime"] == mt:
        return _cache["data"]  # unchanged since last read
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _log.warning("cluster_map.file_unreadable", path=str(p))
        return None
    _cache["mtime"], _cache["data"] = mt, data
    return data


def _save_file(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)  # atomic
    _cache["mtime"], _cache["data"] = p.stat().st_mtime, data


def _build(k: int) -> dict:
    from kg_retrievers.corpus_topic_map import fetch_and_build

    data = fetch_and_build(k=k)
    if data.get("total"):
        _save_file(data)
    return data


@router.get("")
def cluster_map(
    refresh: bool = Query(default=False, description="rebuild from the vector store"),
    k: int = Query(default=12, ge=2, le=24, description="number of topic clusters"),
) -> dict:
    """Return the corpus topic map (cached; builds once if missing, or on ``refresh``)."""
    if not refresh:
        cached = _load_file()
        if cached is not None:
            return {**cached, "cached": True}
    data = _build(k)
    return {**data, "cached": False}
