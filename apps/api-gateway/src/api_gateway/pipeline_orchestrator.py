"""Живой оркестратор ingestion с пер-стадийным статусом (§5.10).

Демонстрирует реальный конвейер приёма документа как последовательность
наблюдаемых *ops* (стадий) — как это делает Dagster-job ``document_ingestion``
из §5.10 (``register_source → docling_parse → store_parsed → chunk → extract``),
но без запущенного Dagster-демона: те же реальные шаги гоняются в фоновом потоке
прямо в api-gateway под живым server-профилем (Neo4j :8000).

Каждая стадия — настоящая работа, переиспользующая готовые модули ingestion:

* ``register_source`` — sha1 файла + генерация ``source_id`` (идемпотентный ключ);
* ``parse``          — :func:`ingestion_service.parsers.parse_document`
                        (Docling/pdfplumber/docx/pptx/xlsx) → :class:`ParsedDoc`;
* ``store``          — persist parsed sidecar (raw+parsed артефакт под ``uploads/``);
* ``chunk``          — :func:`ingestion_service.chunker.chunk_pages`
                        (structure-aware чанкинг §5.9) → превью числа чанков;
* ``extract``        — :class:`ingestion_service.pipeline.IngestionPipeline`
                        пишет сущности/измерения/evidence в живой граф (§9.2 Step 4).

Статус каждой стадии (``pending → running → succeeded | failed | skipped |
cancelled``) обновляется по мере выполнения и виден через polling-endpoint,
поэтому фронт рисует живой прогресс-бар этапов, а не чёрный ящик.

Коарс-статус той же задачи дополнительно зеркалится в общий
:class:`kg_common.storage.jobs.JobStore` (тот же ``jobs.db``, что читает
``GET /api/v1/ingest/jobs/{job_id}``) через её публичный API — без правок стора.
Отмена (``cancel``) выставляет событие, которое проверяется между стадиями:
run переходит в ``cancelled`` и оставшиеся ops помечаются ``cancelled``.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kg_common import get_logger, get_settings, make_id

_log = get_logger("ingest.orchestrator")

# -- канонические стадии конвейера (§5.10 ops, отображённые на parse→store→chunk→extract)
STAGE_OPS: tuple[tuple[str, str], ...] = (
    ("register_source", "Регистрация источника"),
    ("parse", "Разбор (Docling)"),
    ("store", "Сохранение raw+parsed"),
    ("chunk", "Разбиение на чанки"),
    ("extract", "Извлечение в граф"),
)

# Статусы одной стадии.
STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_SUCCEEDED = "succeeded"
STAGE_FAILED = "failed"
STAGE_SKIPPED = "skipped"
STAGE_CANCELLED = "cancelled"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _Cancelled(Exception):
    """Внутренний сигнал отмены между стадиями (§5.10 cancel)."""


@dataclass
class StageRun:
    """Наблюдаемая стадия одного прогона (§5.10 op)."""

    op: str
    label: str
    status: str = STAGE_PENDING
    started_at: str | None = None
    finished_at: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineRun:
    """Один прогон конвейера приёма — задача (§5.10)."""

    run_id: str
    filename: str
    status: str = "running"  # running | succeeded | failed | cancelled
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    doc_id: str | None = None
    source_id: str | None = None
    stages: list[StageRun] = field(default_factory=list)
    error: str | None = None

    def progress(self) -> float:
        """Доля завершённых стадий в ``[0, 1]`` для агрегированного прогресс-бара."""
        if not self.stages:
            return 0.0
        done = sum(
            1
            for s in self.stages
            if s.status in (STAGE_SUCCEEDED, STAGE_SKIPPED)
        )
        return round(done / len(self.stages), 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "filename": self.filename,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "doc_id": self.doc_id,
            "source_id": self.source_id,
            "progress": self.progress(),
            "stages": [s.as_dict() for s in self.stages],
            "error": self.error,
        }


class PipelineOrchestrator:
    """Реестр прогонов + фоновая прогонка реального конвейера (§5.10).

    Единственный процесс-локальный синглтон: держит прогоны в памяти под
    блокировкой и зеркалит каждый на диск (``runtime_dir/pipeline_runs``), так
    что polling видит живое состояние, а список переживает рестарт воркера.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, PipelineRun] = {}
        self._cancels: dict[str, threading.Event] = {}

    # -- пути --------------------------------------------------------------
    def _dir(self) -> Path:
        d = Path(get_settings().runtime_dir) / "pipeline_runs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _persist(self, run: PipelineRun) -> None:
        run.updated_at = _now()
        try:
            (self._dir() / f"{run.run_id}.json").write_text(
                json.dumps(run.as_dict(), ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:  # диск — best-effort; память остаётся источником правды
            _log.warning("orchestrator.persist_failed", run_id=run.run_id, error=str(exc)[:120])

    # -- JobStore зеркало (общий jobs.db, §5.6/§14.10) ---------------------
    def _jobstore(self):  # type: ignore[no-untyped-def]
        from kg_common.storage.jobs import JobStore

        path = f"{get_settings().runtime_dir}/jobs.db"
        js = JobStore(f"sqlite:///{path}")
        js.migrate()
        return js

    def _mirror_job(self, run: PipelineRun) -> None:
        """Отразить коарс-статус в общий JobStore через её публичный API (без правок)."""
        try:
            js = self._jobstore()
            if js.get_job(run.run_id) is None:
                js.create_job(run.run_id, "ingest", total=len(run.stages) or len(STAGE_OPS))
            done = sum(1 for s in run.stages if s.status in (STAGE_SUCCEEDED, STAGE_SKIPPED))
            status_map = {
                "running": "running",
                "succeeded": "succeeded",
                "failed": "failed",
                "cancelled": "cancelled",
            }
            js.update_progress(run.run_id, done=done, status=status_map.get(run.status, "running"))
            if run.error and run.status == "failed":
                js.set_status(run.run_id, "failed", error=run.error)
        except Exception as exc:  # зеркало — best-effort, не роняем прогон
            _log.warning("orchestrator.job_mirror_failed", run_id=run.run_id, error=str(exc)[:120])

    # -- реестр ------------------------------------------------------------
    def get(self, run_id: str) -> PipelineRun | None:
        with self._lock:
            run = self._runs.get(run_id)
        if run is not None:
            return run
        # переживший рестарт прогон — читаем с диска (терминальный снимок)
        p = self._dir() / f"{run_id}.json"
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return _run_from_dict(data)

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        with self._lock:
            for r in self._runs.values():
                seen[r.run_id] = r.as_dict()
        for p in self._dir().glob("*.json"):
            if p.stem in seen:
                continue
            try:
                seen[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
        rows = sorted(seen.values(), key=lambda d: d.get("created_at", ""), reverse=True)
        return rows[: max(1, min(limit, 200))]

    def cancel(self, run_id: str) -> bool:
        """Запросить отмену прогона (проверяется между стадиями). §5.10 cancel."""
        with self._lock:
            ev = self._cancels.get(run_id)
        if ev is None:
            return False
        ev.set()
        return True

    # -- запуск ------------------------------------------------------------
    def start(self, path: Path, *, use_llm: bool = False) -> PipelineRun:
        """Создать прогон и запустить конвейер в фоновом потоке (§5.10)."""
        run_id = f"pipe:{uuid.uuid4().hex[:12]}"
        run = PipelineRun(
            run_id=run_id,
            filename=path.name,
            stages=[StageRun(op=k, label=lbl) for k, lbl in STAGE_OPS],
        )
        cancel = threading.Event()
        with self._lock:
            self._runs[run_id] = run
            self._cancels[run_id] = cancel
        self._persist(run)
        self._mirror_job(run)
        t = threading.Thread(
            target=self._run_pipeline,
            args=(run, path, use_llm, cancel),
            name=f"ingest-{run_id}",
            daemon=True,
        )
        t.start()
        return run

    # -- фоновая прогонка --------------------------------------------------
    def _run_pipeline(
        self, run: PipelineRun, path: Path, use_llm: bool, cancel: threading.Event
    ) -> None:
        ctx: dict[str, Any] = {}
        try:
            self._stage(run, cancel, "register_source", self._op_register, path, ctx)
            run.source_id = ctx.get("source_id")
            self._stage(run, cancel, "parse", self._op_parse, path, ctx)
            self._stage(run, cancel, "store", self._op_store, path, ctx)
            run.doc_id = ctx.get("doc_id")
            self._stage(run, cancel, "chunk", self._op_chunk, path, ctx)

            def _extract(p: Path, c: dict[str, Any]) -> dict[str, Any]:
                return self._op_extract(p, c, use_llm)

            self._stage(run, cancel, "extract", _extract, path, ctx)
            run.status = "succeeded"
        except _Cancelled:
            run.status = "cancelled"
            for s in run.stages:
                if s.status in (STAGE_PENDING, STAGE_RUNNING):
                    s.status = STAGE_CANCELLED
                    s.finished_at = _now()
        except Exception as exc:  # пер-стадийная ошибка уже записана в _stage
            run.status = "failed"
            run.error = run.error or str(exc)[:300]
        finally:
            run.updated_at = _now()
            self._persist(run)
            self._mirror_job(run)

    def _stage(
        self,
        run: PipelineRun,
        cancel: threading.Event,
        op: str,
        fn: Callable[[Path, dict[str, Any]], dict[str, Any]],
        path: Path,
        ctx: dict[str, Any],
    ) -> None:
        if cancel.is_set():
            raise _Cancelled()
        stage = next(s for s in run.stages if s.op == op)
        stage.status = STAGE_RUNNING
        stage.started_at = _now()
        self._persist(run)
        try:
            detail = fn(path, ctx)
        except _Cancelled:
            raise
        except Exception as exc:
            stage.status = STAGE_FAILED
            stage.error = str(exc)[:300]
            stage.finished_at = _now()
            run.error = f"{op}: {stage.error}"
            self._persist(run)
            _log.warning("orchestrator.stage_failed", run_id=run.run_id, op=op, error=stage.error)
            raise
        stage.status = detail.pop("_status", STAGE_SUCCEEDED)
        stage.detail = detail
        stage.finished_at = _now()
        self._persist(run)
        self._mirror_job(run)
        if cancel.is_set():
            raise _Cancelled()

    # -- реальные ops ------------------------------------------------------
    def _op_register(self, path: Path, ctx: dict[str, Any]) -> dict[str, Any]:
        h = hashlib.sha1()
        size = 0
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
                size += len(chunk)
        digest = h.hexdigest()[:16]
        source_id = make_id("Paper", digest)
        ctx["file_hash"] = digest
        ctx["source_id"] = source_id
        return {"source_id": source_id, "sha1": digest, "size_bytes": size}

    def _op_parse(self, path: Path, ctx: dict[str, Any]) -> dict[str, Any]:
        from ingestion_service.parsers import parse_document

        parsed = parse_document(path)
        if parsed is None:
            raise ValueError("документ не удалось разобрать (unsupported/empty)")
        ctx["parsed"] = parsed
        return {
            "title": parsed.title,
            "doc_type": parsed.doc_type,
            "lang": parsed.lang,
            "pages": len(parsed.pages),
            "tables": len(parsed.tables),
            "year": parsed.year,
            "country": parsed.country,
        }

    def _op_store(self, path: Path, ctx: dict[str, Any]) -> dict[str, Any]:
        parsed = ctx["parsed"]
        doc_id = make_id("Document", parsed.file_hash)
        ctx["doc_id"] = doc_id
        uploads = Path(get_settings().runtime_dir) / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        sidecar = uploads / f"{doc_id.replace(':', '_')}.json"
        payload = {
            "doc_id": doc_id,
            "title": parsed.title,
            "doc_type": parsed.doc_type,
            "lang": parsed.lang,
            "country": parsed.country,
            "year": parsed.year,
            "file_hash": parsed.file_hash,
            "source_path": str(path),
            "page_count": len(parsed.pages),
            "status": "parsed",
            "extractor": "rule",
            "pages": [{"page": p, "text": t} for p, t in parsed.pages],
            "tables": [{"page": t.page, "rows": t.rows} for t in parsed.tables],
        }
        sidecar.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return {"doc_id": doc_id, "sidecar": sidecar.name, "page_count": len(parsed.pages)}

    def _op_chunk(self, path: Path, ctx: dict[str, Any]) -> dict[str, Any]:
        from ingestion_service.chunker import chunk_pages

        parsed = ctx["parsed"]
        chunks = chunk_pages(parsed.pages)
        ctx["chunk_count"] = len(chunks)
        chars = sum(len(c.text) for c in chunks)
        return {
            "chunks": len(chunks),
            "total_chars": chars,
            "avg_chars": round(chars / len(chunks)) if chunks else 0,
        }

    def _op_extract(self, path: Path, ctx: dict[str, Any], use_llm: bool) -> dict[str, Any]:
        from ingestion_service.pipeline import IngestionPipeline

        from api_gateway.deps import get_store

        parsed = ctx["parsed"]
        pipe = IngestionPipeline(get_store(), use_llm=use_llm, llm_max_chunks=3 if use_llm else 0)
        res = pipe.ingest(parsed)
        if res.get("status") == "skipped":
            # документ уже в графе — идемпотентность (§5.10): стадия skipped, не failed
            return {"_status": STAGE_SKIPPED, "reason": "duplicate", **res}
        stats = res if isinstance(res, dict) else {}
        return {
            "status": stats.get("status", "ok"),
            "chunks": stats.get("chunks"),
            "entities": stats.get("entities"),
            "measurements": stats.get("measurements"),
            "evidence": stats.get("evidence"),
        }


def _run_from_dict(data: dict[str, Any]) -> PipelineRun:
    """Восстановить :class:`PipelineRun` из дискового снимка (терминальный)."""
    stages = [
        StageRun(
            op=s.get("op", ""),
            label=s.get("label", ""),
            status=s.get("status", STAGE_PENDING),
            started_at=s.get("started_at"),
            finished_at=s.get("finished_at"),
            detail=s.get("detail", {}) or {},
            error=s.get("error"),
        )
        for s in data.get("stages", [])
    ]
    return PipelineRun(
        run_id=data.get("run_id", ""),
        filename=data.get("filename", ""),
        status=data.get("status", "succeeded"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        doc_id=data.get("doc_id"),
        source_id=data.get("source_id"),
        stages=stages,
        error=data.get("error"),
    )


# Процесс-локальный синглтон (§5.10).
_ORCHESTRATOR: PipelineOrchestrator | None = None


def orchestrator() -> PipelineOrchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = PipelineOrchestrator()
    return _ORCHESTRATOR
