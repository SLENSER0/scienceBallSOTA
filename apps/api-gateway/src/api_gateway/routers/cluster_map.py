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

from fastapi import APIRouter, Depends, Query

from api_gateway.auth import current_role
from kg_common import get_logger, get_settings
from kg_schema.enums import Role

router = APIRouter(prefix="/api/v1/cluster-map", tags=["cluster-map"])
_log = get_logger("cluster_map")

# The map is a precomputed artifact; k is fixed here and set via the precompute script.
_DEFAULT_K = 12
# Roles that may see raw chunk text and trigger a rebuild (mirrors agent access policy).
_FULL_ACCESS = {Role.RESEARCHER, Role.ANALYST, Role.PROJECT_MANAGER, Role.ADMIN, Role.CURATOR}

# Per-process cache: (mtime, payload). Invalidated when the durable file changes.
_cache: dict[str, Any] = {"mtime": None, "data": None}


def _full_access(role: str) -> bool:
    return role in _FULL_ACCESS or role == "admin"


def _redact(data: dict, full: bool) -> dict:
    """For restricted roles, drop raw chunk text (``points[].t``) — coordinates and
    cluster labels stay, so the visualization works without leaking corpus text
    (§24.14: external partners never see raw passage text)."""
    if full:
        return data
    pts = [{key: v for key, v in p.items() if key != "t"} for p in data.get("points", [])]
    return {**data, "points": pts, "text_redacted": True}


_EMPTY = {"points": [], "clusters": [], "total": 0, "shown": 0, "var3d": 0.0, "k": 0}


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


def _build() -> dict:
    """Build the default-k topic map from the vector store and persist it (never a
    non-default k, so a rebuild can't poison the shared artifact). Degrades to an empty
    payload on any build error instead of 500-ing."""
    from kg_retrievers.corpus_topic_map import fetch_and_build

    try:
        data = fetch_and_build(k=_DEFAULT_K)
    except Exception as exc:
        _log.warning("cluster_map.build_failed", error=str(exc)[:150])
        return dict(_EMPTY)
    if data.get("total"):
        _save_file(data)
    return data


@router.get("")
def cluster_map(
    refresh: bool = Query(default=False, description="rebuild (full-access roles only)"),
    role: str = Depends(current_role),
) -> dict:
    """Return the corpus topic map, cached from a durable file (builds once if missing).

    Raw chunk text is withheld from restricted roles, and only full-access roles may
    trigger a rebuild (an unauthenticated rebuild would be both a DoS and a shared-state
    write on the hot path).
    """
    full = _full_access(role)
    if not (refresh and full):
        cached = _load_file()
        if cached is not None:
            return {**_redact(cached, full), "cached": True}
    data = _build()
    return {**_redact(data, full), "cached": False}
