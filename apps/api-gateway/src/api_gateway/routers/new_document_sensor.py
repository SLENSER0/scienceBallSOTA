"""new_document_sensor — файл в kg-raw → авто-запуск full_ingestion_job → граф растёт вживую (§9.6).

The demo promise is «кинул PDF в папку — граф сам вырос»: an operator drops a
document into a watched folder and, on the next sensor tick, that file is parsed and
run through the **real** per-document ingestion pipeline, the knowledge graph gains
nodes/edges, and the growth is reported live — before/after graph counts plus the
per-file delta.

Nothing here re-implements ingestion or the sensor primitives; it is the live,
server-profile (Neo4j :8000) wiring around pieces that already exist:

* the pure sensor watermark/emit primitives in ``kg_common`` —
  :class:`kg_common.sensor_cursor.SensorCursor` (+ :func:`new_items` /
  :func:`advance_cursor`) for idempotent «what appeared since last tick»,
  :class:`kg_common.sensor_spec.SensorSpec` + :func:`should_trigger` for the
  file-kind trigger gate, and :func:`kg_common.run_request.build_run_requests` to
  emit one deduped ``RunRequest`` per new document against ``full_ingestion_job``;
* the ingestion pipeline — ``ingestion_service.parsers.parse_document`` and
  ``ingestion_service.pipeline.IngestionPipeline`` (content-hash dedup, so a re-drop
  never duplicates the graph — it surfaces as ``skipped``);
* the shared graph store from :func:`api_gateway.deps.get_store` (the live graph the
  UI reads elsewhere).

Idempotency is двойная: the sensor cursor advances past monotonic per-file tokens
(``<mtime_ns>::<name>``) so a re-poll never re-processes a file, and each emitted
``RunRequest.run_key`` is the deterministic content ``doc_id`` so even a same-content
re-drop under a new name is a no-op run. The cursor + processed set + recent events
are persisted to a small JSON file under ``runtime_dir`` so state survives restarts.

Endpoints (prefix ``/api/v1/new-document-sensor``):

* ``GET  /status``  — watched dir, cursor, enabled, pending (dropped-but-unprocessed)
  files, current live graph counts, recent events.
* ``POST /upload``  — drop a file into the watched folder (multipart). Returns its name.
* ``POST /poll``    — one sensor tick: ingest every new file, grow the graph, report
  the before/after counts and per-file deltas + emitted run requests.
* ``POST /enable`` / ``POST /disable`` — gate the sensor (a disabled sensor skips).
* ``POST /reset``   — rewind the cursor (keep the files) so the demo can re-run.
* ``GET  /events``  — recent detection/ingest events (newest first).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store
from kg_common import get_logger, get_settings, make_id
from kg_common.run_request import build_run_requests
from kg_common.sensor_cursor import SensorCursor, advance_cursor, new_items
from kg_common.sensor_spec import SensorSpec, should_trigger

router = APIRouter(prefix="/api/v1/new-document-sensor", tags=["new-document-sensor"])
_log = get_logger("api.new_document_sensor")

SENSOR_NAME = "new_document_sensor"
JOB_NAME = "full_ingestion_job"

# Write-capable roles — same set as single/batch document ingestion (§19).
_CAN_INGEST = {"admin", "curator", "researcher", "analyst", "project_manager"}
# Parseable extensions — mirror ingestion_service.parsers.SUPPORTED.
_ALLOWED_SUFFIX = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".md"}
_MAX_BYTES = 64 * 1024 * 1024  # 64 MB per file
_MAX_EVENTS = 200  # keep the recent-events ring bounded
_MAX_PER_POLL = 25  # cap one tick so a huge drop stays bounded

_LOCK = threading.Lock()  # serialize polls (they mutate the shared graph + cursor)


def _require_ingest(role: str) -> None:
    if role not in _CAN_INGEST:
        raise HTTPException(status_code=403, detail="role may not drive the ingestion sensor")


def _watched_dir() -> Path:
    """The kg-raw drop folder (created on demand) under the runtime dir."""
    d = Path(get_settings().runtime_dir) / "kg-raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path() -> Path:
    return Path(get_settings().runtime_dir) / "new_document_sensor_state.json"


def _default_state() -> dict[str, Any]:
    return {
        "cursor": SensorCursor(name=SENSOR_NAME, position="").as_dict(),
        "enabled": True,
        "processed": [],  # run_keys (doc_ids) already emitted — belt-and-suspenders idempotency
        "events": [],  # recent detection/ingest events, newest last
    }


def _load_state() -> dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return _default_state()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _log.warning("new_document_sensor.state_unreadable", path=str(p))
        return _default_state()
    base = _default_state()
    base.update({k: data[k] for k in ("cursor", "enabled", "processed", "events") if k in data})
    return base


def _save_state(state: dict[str, Any]) -> None:
    state["events"] = state["events"][-_MAX_EVENTS:]
    state["processed"] = state["processed"][-2000:]
    tmp = _state_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(_state_path())


def _token(path: Path) -> str:
    """Monotonic per-file token: newer files sort strictly after older ones.

    ``<mtime_ns zero-padded>::<name>`` — lexicographic order over these strings
    matches drop order, so the sensor cursor treats exactly the freshly-dropped
    files as new (idempotent re-poll — a seen file is never re-processed).
    """
    return f"{path.stat().st_mtime_ns:022d}::{path.name}"


def _listing() -> list[tuple[str, Path]]:
    """(token, path) for every parseable file in the watched dir, sorted by token."""
    out: list[tuple[str, Path]] = []
    for p in _watched_dir().iterdir():
        if p.is_file() and p.suffix.lower() in _ALLOWED_SUFFIX:
            out.append((_token(p), p))
    out.sort(key=lambda t: t[0])
    return out


def _event(kind: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, "at": time.time(), **fields}


def _status_payload(state: dict[str, Any]) -> dict[str, Any]:
    cursor = SensorCursor.from_dict(state["cursor"])
    listing = _listing()
    pending = [
        {"file": p.name, "token": tok, "size": p.stat().st_size}
        for tok, p in listing
        if tok in new_items(cursor.position, [tok])
    ]
    store = get_store()
    counts = store.counts()
    return {
        "sensor": SENSOR_NAME,
        "job_name": JOB_NAME,
        "enabled": bool(state["enabled"]),
        "watched_dir": str(_watched_dir()),
        "cursor": cursor.as_dict(),
        "files_present": len(listing),
        "pending": pending,
        "pending_count": len(pending),
        "graph": {"nodes": counts.get("nodes", 0), "rels": counts.get("rels", 0)},
        "recent_events": list(reversed(state["events"][-30:])),
    }


# -- request bodies --------------------------------------------------------
class PollBody(BaseModel):
    use_llm: bool = False  # rule-only by default; LLM enrichment is opt-in (slower)


# -- endpoints -------------------------------------------------------------
@router.get("/status")
def status() -> dict:
    """Live sensor status: watched dir, cursor, pending files, current graph counts."""
    with _LOCK:
        return _status_payload(_load_state())


@router.get("/events")
def events(limit: int = Query(default=50, ge=1, le=_MAX_EVENTS)) -> dict:
    """Recent detection/ingest events, newest first."""
    with _LOCK:
        state = _load_state()
    evs = list(reversed(state["events"]))[:limit]
    return {"events": evs, "count": len(evs)}


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Drop one document into the kg-raw folder — the sensor picks it up on the next poll."""
    _require_ingest(role)
    name = Path(file.filename or "document").name
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIX:
        raise HTTPException(status_code=422, detail=f"unsupported type: {suffix or 'none'}")
    dest = _watched_dir() / name
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > _MAX_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="file too large (max 64 MB)")
                out.write(chunk)
    except HTTPException:
        raise
    with _LOCK:
        state = _load_state()
        state["events"].append(_event("dropped", file=name, size=size, by=user))
        _save_state(state)
    audit.record("new_document_dropped", user=user, role=role, detail={"file": name, "size": size})
    return {"file": name, "size": size, "watched_dir": str(_watched_dir())}


@router.post("/poll")
def poll(
    body: PollBody | None = None,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """One sensor tick: ingest every new file, grow the live graph, report the deltas."""
    _require_ingest(role)
    use_llm = bool(body.use_llm) if body else False

    with _LOCK:
        state = _load_state()
        if not state["enabled"]:
            return {"triggered": False, "reason": "sensor disabled", **_status_payload(state)}

        cursor = SensorCursor.from_dict(state["cursor"])
        listing = _listing()
        tokens = [tok for tok, _ in listing]
        latest = tokens[-1] if tokens else ""

        # File-kind trigger gate (§9.6): fire only when a token newer than the
        # watermark exists. Pure predicate — no clock, no re-scan surprises.
        spec = SensorSpec(
            name=SENSOR_NAME, kind="file", config={"last_seen": cursor.position}, enabled=True
        )
        if not should_trigger(spec, {"latest": latest}):
            return {"triggered": False, "reason": "no new files", **_status_payload(state)}

        fresh_tokens = set(new_items(cursor.position, tokens))
        fresh = [(tok, p) for tok, p in listing if tok in fresh_tokens][:_MAX_PER_POLL]

        store = get_store()
        before = store.counts()
        from ingestion_service.parsers import parse_document
        from ingestion_service.pipeline import IngestionPipeline

        pipe = IngestionPipeline(store, use_llm=use_llm, llm_max_chunks=3 if use_llm else 0)
        results: list[dict[str, Any]] = []
        run_keys: list[str] = []
        for tok, path in fresh:
            b = store.counts()
            entry: dict[str, Any] = {"file": path.name, "token": tok, "doc_id": None}
            try:
                parsed = parse_document(path)
                if parsed is None:
                    entry.update(status="failed", error="could not parse document")
                else:
                    doc_id = make_id("Document", parsed.file_hash)
                    entry["doc_id"] = doc_id
                    entry["title"] = parsed.title
                    run_keys.append(doc_id)
                    res = pipe.ingest(parsed)
                    a = store.counts()
                    entry["nodes_added"] = a.get("nodes", 0) - b.get("nodes", 0)
                    entry["rels_added"] = a.get("rels", 0) - b.get("rels", 0)
                    entry["chunks"] = res.get("chunks", 0)
                    if res.get("status") == "skipped":
                        entry["status"] = "duplicate"  # content already in the graph
                    elif res.get("status") == "ok":
                        entry["status"] = "ingested"
                    else:
                        entry.update(status="failed", error=f"status: {res.get('status')!r}")
            except Exception as exc:  # never let one bad file abort the tick
                _log.warning("new_document_sensor.doc_failed", file=path.name, error=str(exc)[:160])
                entry.update(status="failed", error=str(exc)[:200])
            results.append(entry)
            state["events"].append(
                _event(
                    "ingested",
                    file=path.name,
                    status=entry.get("status"),
                    doc_id=entry.get("doc_id"),
                    nodes_added=entry.get("nodes_added", 0),
                    rels_added=entry.get("rels_added", 0),
                )
            )

        # Emit one deduped RunRequest per new document against full_ingestion_job.
        already = frozenset(state["processed"])
        run_requests = build_run_requests(JOB_NAME, run_keys, already_requested=already)
        state["processed"].extend(rq.run_key for rq in run_requests)

        # Advance the watermark past everything seen this tick (idempotent re-poll).
        state["cursor"] = advance_cursor(cursor, tokens).as_dict()
        after = store.counts()
        _save_state(state)

        payload_status = _status_payload(state)

    _log.info(
        "new_document_sensor.poll",
        processed=len(results),
        nodes_delta=after.get("nodes", 0) - before.get("nodes", 0),
    )
    audit.record(
        "new_document_sensor_poll",
        user=user,
        role=role,
        detail={"processed": len(results), "runs": len(run_requests)},
    )
    return {
        "triggered": True,
        "processed": len(results),
        "results": results,
        "run_requests": [rq.as_dict() for rq in run_requests],
        "graph_before": {"nodes": before.get("nodes", 0), "rels": before.get("rels", 0)},
        "graph_after": {"nodes": after.get("nodes", 0), "rels": after.get("rels", 0)},
        "graph_growth": {
            "nodes": after.get("nodes", 0) - before.get("nodes", 0),
            "rels": after.get("rels", 0) - before.get("rels", 0),
        },
        **payload_status,
    }


@router.post("/enable")
def enable(role: str = Depends(current_role)) -> dict:
    """Enable the sensor (polls will trigger on new files)."""
    _require_ingest(role)
    with _LOCK:
        state = _load_state()
        state["enabled"] = True
        state["events"].append(_event("enabled"))
        _save_state(state)
        return _status_payload(state)


@router.post("/disable")
def disable(role: str = Depends(current_role)) -> dict:
    """Disable the sensor (polls skip regardless of pending files)."""
    _require_ingest(role)
    with _LOCK:
        state = _load_state()
        state["enabled"] = False
        state["events"].append(_event("disabled"))
        _save_state(state)
        return _status_payload(state)


@router.post("/reset")
def reset(role: str = Depends(current_role), user: str = Depends(current_user)) -> dict:
    """Rewind the cursor + processed set (keep the files) so the demo can re-run.

    The graph is not touched; re-ingesting the same files is a content-hash no-op
    (they surface as ``duplicate``), so this only makes the pending list re-appear.
    """
    _require_ingest(role)
    with _LOCK:
        state = _load_state()
        state["cursor"] = SensorCursor(name=SENSOR_NAME, position="").as_dict()
        state["processed"] = []
        state["events"].append(_event("reset", by=user))
        _save_state(state)
        audit.record("new_document_sensor_reset", user=user, role=role, detail={})
        return _status_payload(state)
