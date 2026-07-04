"""Живой пер-стадийный статус ingestion-конвейера (§5.10).

Фасад над :mod:`api_gateway.pipeline_orchestrator`: загрузка документа запускает
реальный конвейер приёма (``register_source → parse → store → chunk → extract``)
в фоновом потоке под живым server-профилем (Neo4j :8000), а polling-эндпоинт
отдаёт статус каждой стадии, чтобы UI рисовал прогресс-бар этапов вместо чёрного
ящика. Коарс-статус той же задачи зеркалится в общий ``jobs.db`` (§5.6), так что
``GET /api/v1/ingest/jobs/{run_id}`` тоже отражает прогресс.

Эндпоинты (все под ``/api/v1/ingest/pipeline``):

* ``POST /upload``            — multipart-файл → старт прогона, ``{run_id, ...}``;
* ``GET  /{run_id}``          — живой статус прогона со списком стадий;
* ``POST /{run_id}/cancel``   — запросить отмену (проверяется между стадиями);
* ``GET  /``                  — недавние прогоны (для истории/списка);
* ``GET  /meta/stages``       — статический план стадий конвейера (для легенды).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.pipeline_orchestrator import STAGE_OPS, orchestrator
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/ingest/pipeline", tags=["ingest-pipeline"])

# Те же write-роли, что и обычная загрузка документа (§19 / documents.py).
_CAN_UPLOAD = {"admin", "curator", "researcher", "analyst", "project_manager"}
_MAX_BYTES = 64 * 1024 * 1024  # 64 MB, как и /documents/upload
_ALLOWED_SUFFIX = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md"}


def _staging_dir() -> Path:
    d = Path(get_settings().runtime_dir) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/meta/stages")
def stage_plan() -> dict:
    """Статический план стадий конвейера (§5.10) — для легенды/скелета UI."""
    return {"stages": [{"op": op, "label": label} for op, label in STAGE_OPS]}


@router.get("")
def list_runs(limit: int = 30) -> dict:
    """Недавние прогоны конвейера (новейшие первыми)."""
    rows = orchestrator().list_runs(limit=limit)
    return {"runs": rows, "count": len(rows)}


@router.get("/{run_id}")
def run_status(run_id: str) -> dict:
    """Живой статус одного прогона со стадиями (§5.10)."""
    run = orchestrator().get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return run.as_dict()


@router.post("/{run_id}/cancel")
def cancel_run(
    run_id: str,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Запросить отмену прогона; переход в ``cancelled`` между стадиями (§5.10)."""
    if role not in _CAN_UPLOAD:
        raise HTTPException(status_code=403, detail="role may not control ingestion")
    orch = orchestrator()
    run = orch.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    orch.cancel(run_id)
    audit.record("ingest_pipeline_cancel", user=user, role=role, detail={"run_id": run_id})
    return orch.get(run_id).as_dict()


@router.post("/upload")
async def upload_and_run(
    file: UploadFile = File(...),
    use_llm: bool = False,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Принять документ и запустить пер-стадийный конвейер приёма (§5.10)."""
    if role not in _CAN_UPLOAD:
        raise HTTPException(status_code=403, detail="role may not upload documents")
    name = Path(file.filename or "document").name
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIX:
        raise HTTPException(status_code=415, detail=f"unsupported file type: {suffix or 'none'}")

    dest = _staging_dir() / name
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > _MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file too large (max 64 MB)")
            out.write(chunk)

    run = orchestrator().start(dest, use_llm=use_llm)
    audit.record(
        "ingest_pipeline_start",
        user=user,
        role=role,
        detail={"run_id": run.run_id, "filename": name},
    )
    return run.as_dict()
