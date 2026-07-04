"""Batch/bulk directory ingestion with an aggregated report (§5.10 / §19).

Drop 20–50 documents (or point at a server-side corpus directory) and run the whole
set through the **real** per-document ingestion pipeline in one pass, then read a single
summary: how many were attempted / finished / skipped-as-duplicate / failed, how many
chunks · entities · measurements · facts were extracted across the batch, and the running
throughput in docs/min. This is the operator-facing wrapper around the pieces that already
exist — ``ingestion_service.parsers.parse_document``, ``ingestion_service.pipeline.
IngestionPipeline``, ``ingestion_service.cli.discover`` and
``ingestion_service.batch_ingest_report.build_batch_report`` — plus the shared
``JobStore`` (§5.6) for live status/progress/cancel. Nothing here re-implements ingestion;
it only fans a directory out over the pipeline and folds the per-doc results into one report.

A batch is long-running, so it executes on a background thread: the POST returns a
``job_id`` immediately and the client polls ``GET /report/{job_id}`` for live progress and
the growing aggregate. Cancellation is cooperative — the worker checks the job's status
between documents and stops when it turns ``cancelled``. Writes go to whichever store
``get_store()`` returns (server-profile Neo4j :8000 in the live deployment); the pipeline
dedups by document content hash, so re-running a batch never duplicates nodes (duplicates
surface in the report instead).

Пакетная загрузка каталога с агрегированным отчётом (§5.10): прогоняет 20–50 документов
через настоящий per-doc конвейер и сворачивает результаты в одну сводку (готово / дубликаты /
ошибки, извлечённые чанки·сущности·факты, docs/min). Фоновая задача + опрос отчёта; отмена
кооперативная; дедупликация по content-hash — повторный прогон не плодит узлы.
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store
from kg_common import get_logger, get_settings

router = APIRouter(prefix="/api/v1/batch-ingest", tags=["batch-ingest"])
_log = get_logger("api.batch_ingest")

# Same write-capable roles as single-document upload (§19 / documents.py).
_CAN_INGEST = {"admin", "curator", "researcher", "analyst", "project_manager"}
# Parseable extensions (mirror ingestion_service.parsers.SUPPORTED).
_ALLOWED_SUFFIX = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".md"}
_MAX_BYTES = 64 * 1024 * 1024  # 64 MB per file
_MAX_FILES = 60  # a batch is meant for 20–50 docs; cap to keep one run bounded

# In-process per-job state (results + extraction tally + timing). Keyed by job_id.
# The JobStore owns lifecycle/progress; this holds the richer aggregate the report needs.
_STATE: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_cache: dict[str, Any] = {}


def _jobs():  # type: ignore[no-untyped-def]
    """Shared ingest JobStore (§5.6) — same SQLite db the /ingest/jobs router uses."""
    if "store" not in _cache:
        from kg_common.storage.jobs import JobStore

        js = JobStore(f"sqlite:///{get_settings().runtime_dir}/jobs.db")
        js.migrate()
        _cache["store"] = js
    return _cache["store"]


def _require_ingest(role: str) -> None:
    if role not in _CAN_INGEST:
        raise HTTPException(status_code=403, detail="role may not run batch ingestion")


def _batch_dir(job_id: str) -> Path:
    d = Path(get_settings().runtime_dir) / "batch_uploads" / job_id.replace(":", "_")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cancelled(job_id: str) -> bool:
    j = _jobs().get_job(job_id)
    return bool(j is not None and j.status == "cancelled")


def _worker(job_id: str, paths: list[str], use_llm: bool) -> None:
    """Background thread: ingest every path, folding results into ``_STATE[job_id]``."""
    from ingestion_service.parsers import parse_document
    from ingestion_service.pipeline import IngestionPipeline

    js = _jobs()
    js.update_progress(job_id, 0, status="running")
    store = get_store()
    # One pipeline per batch — pipe.stats accumulates the extraction tally across all docs.
    pipe = IngestionPipeline(store, use_llm=use_llm, llm_max_chunks=3 if use_llm else 0)
    results: list[dict[str, Any]] = _STATE[job_id]["results"]

    for i, path_str in enumerate(paths, start=1):
        if _cancelled(job_id):
            _log.info("batch_ingest.cancelled", job_id=job_id, at=i)
            break
        path = Path(path_str)
        entry: dict[str, Any] = {"doc_id": None, "title": path.name, "duplicate": False}
        try:
            parsed = parse_document(path)
            if parsed is None:
                entry.update(status="failed", error="could not parse document")
            else:
                from kg_common import make_id

                entry["doc_id"] = make_id("Document", parsed.file_hash)
                entry["title"] = parsed.title
                res = pipe.ingest(parsed)
                status = res.get("status")
                if status == "skipped":  # dedup by content hash — already in the graph
                    entry.update(status="done", duplicate=True, chunks=res.get("chunks", 0))
                elif status == "ok":
                    entry.update(status="done", chunks=res.get("chunks", 0))
                else:
                    entry.update(status="failed", error=f"unexpected status: {status!r}")
        except Exception as exc:  # never let one bad doc abort the batch
            _log.warning("batch_ingest.doc_failed", path=path.name, error=str(exc)[:160])
            entry.update(status="failed", error=str(exc)[:200])

        with _LOCK:
            results.append(entry)
            _STATE[job_id]["extraction"] = pipe.stats.as_dict()
        js.update_progress(job_id, i)

    with _LOCK:
        _STATE[job_id]["finished_at"] = time.time()
        _STATE[job_id]["extraction"] = pipe.stats.as_dict()
    if not _cancelled(job_id):
        done = len(results)
        failed = sum(1 for r in results if r.get("status") == "failed")
        # A batch "succeeds" even with some failed docs; a hard error would set failed.
        js.update_progress(job_id, done, status="succeeded")
        _log.info("batch_ingest.done", job_id=job_id, total=done, failed=failed)


def _start(job_id: str, paths: list[str], use_llm: bool, source: str) -> None:
    """Register job state + JobStore row, then spawn the worker thread."""
    with _LOCK:
        _STATE[job_id] = {
            "results": [],
            "extraction": {},
            "started_at": time.time(),
            "finished_at": None,
            "use_llm": use_llm,
            "source": source,
            "total": len(paths),
        }
    _jobs().create_job(job_id, "batch-ingest", total=len(paths))
    t = threading.Thread(target=_worker, args=(job_id, paths, use_llm), daemon=True)
    t.start()


def _report_payload(job_id: str) -> dict[str, Any]:
    """Fold the current per-doc results into an aggregated §5.10 report."""
    from ingestion_service.batch_ingest_report import build_batch_report

    job = _jobs().get_job(job_id)
    if job is None or job_id not in _STATE:
        raise HTTPException(status_code=404, detail="batch job not found")
    with _LOCK:
        st = _STATE[job_id]
        results = list(st["results"])
        extraction = dict(st["extraction"])
        started_at = st["started_at"]
        finished_at = st["finished_at"]
        total = st["total"]
        use_llm = st["use_llm"]
        source = st["source"]

    report = build_batch_report(results).as_dict()
    elapsed = (finished_at or time.time()) - started_at
    processed = len(results)
    docs_per_min = round(processed / elapsed * 60, 1) if elapsed > 0 and processed else 0.0

    return {
        "job": job.as_dict(),
        "report": report,
        "extraction": extraction,
        "results": results,
        "throughput": {
            "processed": processed,
            "total": total,
            "elapsed_s": round(elapsed, 1),
            "docs_per_min": docs_per_min,
        },
        "use_llm": use_llm,
        "source": source,
    }


# -- request bodies --------------------------------------------------------
class RunBody(BaseModel):
    data_dir: str | None = None  # None → settings.data_dir (the seed corpus)
    limit: int = 30  # cap the number of files pulled from the directory
    use_llm: bool = False  # rule-only by default; LLM enrichment is opt-in (slower)


# -- endpoints -------------------------------------------------------------
@router.get("/discover")
def discover_dir(
    data_dir: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=_MAX_FILES),
) -> dict:
    """Preview a directory: how many ingestable files and a per-extension breakdown."""
    from ingestion_service.cli import discover

    root = data_dir or get_settings().data_dir
    if not Path(root).exists():
        raise HTTPException(status_code=404, detail=f"directory not found: {root}")
    files = discover(root, max_mb=_MAX_BYTES / 1_000_000)
    by_ext: dict[str, int] = {}
    for f in files:
        by_ext[f.suffix.lower()] = by_ext.get(f.suffix.lower(), 0) + 1
    sample = [f.name for f in files[:limit]]
    return {
        "data_dir": str(root),
        "total": len(files),
        "limit": limit,
        "will_ingest": min(len(files), limit),
        "by_ext": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])),
        "sample": sample,
    }


@router.post("/run")
def run_directory(
    body: RunBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Batch-ingest a server-side directory (default: the seed corpus). Returns a job_id."""
    _require_ingest(role)
    from ingestion_service.cli import discover

    root = body.data_dir or get_settings().data_dir
    if not Path(root).exists():
        raise HTTPException(status_code=404, detail=f"directory not found: {root}")
    files = discover(root, max_mb=_MAX_BYTES / 1_000_000)
    limit = max(1, min(body.limit, _MAX_FILES))
    paths = [str(f) for f in files[:limit]]
    if not paths:
        raise HTTPException(status_code=422, detail="no ingestable files in directory")

    job_id = f"batch:{uuid.uuid4().hex[:12]}"
    _start(job_id, paths, body.use_llm, source=f"dir:{root}")
    audit.record(
        "batch_ingest_run", user=user, role=role, detail={"job_id": job_id, "n": len(paths)}
    )
    return {
        "job_id": job_id,
        "total": len(paths),
        "source": f"dir:{root}",
        "use_llm": body.use_llm,
    }


@router.post("/upload")
async def upload_batch(
    files: list[UploadFile] = File(...),
    use_llm: bool = Query(default=False),
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Drop 20–50 documents at once; save them and kick off a batch job. Returns a job_id."""
    _require_ingest(role)
    if not files:
        raise HTTPException(status_code=422, detail="no files uploaded")
    if len(files) > _MAX_FILES:
        raise HTTPException(status_code=413, detail=f"too many files (max {_MAX_FILES})")

    job_id = f"batch:{uuid.uuid4().hex[:12]}"
    dest_dir = _batch_dir(job_id)
    paths: list[str] = []
    skipped: list[dict[str, str]] = []
    for uf in files:
        name = Path(uf.filename or "document").name
        suffix = Path(name).suffix.lower()
        if suffix not in _ALLOWED_SUFFIX:
            skipped.append({"name": name, "reason": f"unsupported type: {suffix or 'none'}"})
            continue
        dest = dest_dir / name
        size = 0
        try:
            with dest.open("wb") as out:
                while chunk := await uf.read(1 << 20):
                    size += len(chunk)
                    if size > _MAX_BYTES:
                        out.close()
                        dest.unlink(missing_ok=True)
                        raise ValueError("file too large (max 64 MB)")
                    out.write(chunk)
        except ValueError as exc:
            skipped.append({"name": name, "reason": str(exc)})
            continue
        paths.append(str(dest))

    if not paths:
        raise HTTPException(status_code=422, detail="no ingestable files in upload")

    _start(job_id, paths, use_llm, source="upload")
    audit.record(
        "batch_ingest_upload", user=user, role=role, detail={"job_id": job_id, "n": len(paths)}
    )
    return {
        "job_id": job_id,
        "total": len(paths),
        "source": "upload",
        "use_llm": use_llm,
        "skipped": skipped,
    }


@router.get("/report/{job_id}")
def batch_report(job_id: str) -> dict:
    """Live aggregated report for a batch job — progress, tally, extraction, throughput."""
    return _report_payload(job_id)


@router.post("/cancel/{job_id}")
def cancel_batch(
    job_id: str,
    role: str = Depends(current_role),
) -> dict:
    """Cooperatively cancel a running batch (worker stops between documents)."""
    _require_ingest(role)
    if _jobs().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="batch job not found")
    _jobs().cancel(job_id)
    return _jobs().get_job(job_id).as_dict()


@router.get("/jobs")
def list_batch_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """Recent batch-ingest jobs (newest first), each with its aggregate counts."""
    rows = _jobs().list_jobs(kind="batch-ingest")
    rows = list(reversed(rows))[:limit]
    out: list[dict[str, Any]] = []
    for j in rows:
        d = j.as_dict()
        st = _STATE.get(j.job_id)
        if st is not None:
            with _LOCK:
                results = list(st["results"])
            d["done_docs"] = sum(1 for r in results if r.get("status") == "done")
            d["failed_docs"] = sum(1 for r in results if r.get("status") == "failed")
            d["duplicates"] = sum(1 for r in results if r.get("duplicate"))
            d["source"] = st["source"]
        out.append(d)
    return {"jobs": out, "count": len(out)}
