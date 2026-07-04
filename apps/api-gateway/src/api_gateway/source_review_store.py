"""Pending low-trust deep-research sources awaiting human review (§23.27).

Sources that Deep Research finds and the user asks to load into the graph are each
run through Source Trust (kg_retrievers.citation_trust). High/medium-trust sources
are ingested directly; **low/untrusted** ones are held HERE — not ingested — until a
curator approves (→ ingest) or rejects (→ dropped). A small JSON ledger under the
runtime dir keeps this dependency-free and avoids migrating the shared review-queue
table on a running database.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from kg_common import get_settings

_LOCK = threading.Lock()

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"


def _path() -> Path:
    root = getattr(get_settings(), "runtime_dir", None) or "var/runtime"
    d = Path(root) / "source_reviews"
    d.mkdir(parents=True, exist_ok=True)
    return d / "pending.json"


def _load() -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # pragma: no cover - corrupt/partial file
        return []


def _save(items: list[dict[str, Any]]) -> None:
    _path().write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")


def source_id(source: dict[str, Any]) -> str:
    """Deterministic id from the source URL (or title) so re-enqueue is idempotent."""
    key = str(source.get("url") or source.get("title") or "").strip().lower()
    return "srcrev:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def enqueue(source: dict[str, Any], trust: dict[str, Any]) -> str:
    """Add (or refresh) a pending low-trust source; returns its id."""
    sid = source_id(source)
    with _LOCK:
        items = [it for it in _load() if it.get("id") != sid]
        items.append({"id": sid, "source": source, "trust": trust, "status": PENDING})
        _save(items)
    return sid


def list_pending() -> list[dict[str, Any]]:
    return [it for it in _load() if it.get("status") == PENDING]


def get(sid: str) -> dict[str, Any] | None:
    return next((it for it in _load() if it.get("id") == sid), None)


def set_status(sid: str, status: str) -> dict[str, Any] | None:
    with _LOCK:
        items = _load()
        found: dict[str, Any] | None = None
        for it in items:
            if it.get("id") == sid:
                it["status"] = status
                found = dict(it)
        if found:
            _save(items)
    return found
