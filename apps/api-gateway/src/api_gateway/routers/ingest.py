"""Ingest job status endpoints (§14.10 / §5.6) — backed by the JobStore."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kg_common import get_settings

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

_cache: dict[str, object] = {}


def _jobs():  # type: ignore[no-untyped-def]
    if "store" not in _cache:
        from kg_common.storage.jobs import JobStore

        path = f"{get_settings().runtime_dir}/jobs.db"
        js = JobStore(f"sqlite:///{path}")
        js.migrate()
        _cache["store"] = js
    return _cache["store"]


class JobCreate(BaseModel):
    kind: str = "ingest"
    total: int = 0


@router.post("/jobs")
def create_job(body: JobCreate) -> dict:
    jid = f"job:{uuid.uuid4().hex[:12]}"
    _jobs().create_job(jid, body.kind, total=body.total)
    return _jobs().get_job(jid).as_dict()


@router.get("/jobs")
def list_jobs(status: str | None = None, kind: str | None = None) -> dict:
    return {"jobs": [j.as_dict() for j in _jobs().list_jobs(status=status, kind=kind)]}


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    j = _jobs().get_job(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="job not found")
    return j.as_dict()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    if _jobs().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    _jobs().cancel(job_id)
    return _jobs().get_job(job_id).as_dict()
