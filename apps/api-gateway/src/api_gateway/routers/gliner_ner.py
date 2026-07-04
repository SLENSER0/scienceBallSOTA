"""Real GLiNER ML-NER over the live corpus (§6.7).

Exposes the process-cached GLiNER extractor (``kg_extractors.gliner``) as three
read-only endpoints so the UI can prove that ML-NER — not just the regex/rule
fallback — is driving entity recall:

* ``GET  /api/v1/ml-ner/status``  — which backend is live (``gliner`` vs
  ``rule``), the checkpoint name, the §8.1 domain labels and the threshold.
* ``POST /api/v1/ml-ner/extract`` — run NER on ad-hoc text; returns anchored
  ``{label, text, char_start, char_end, score}`` mentions + latency.
* ``GET  /api/v1/ml-ner/corpus``  — pull real ``Chunk`` texts from the live Neo4j
  graph, run batched inference, and report the **recall lift** ML gives over the
  rule/regex baseline on the same chunks (the "graph gets denser" signal).

The router only reads: it never mutates the graph. Model config (checkpoint,
threshold, device) is read from settings when present, else sensible defaults, so
it works today on both the embedded and the server (Neo4j :8000) profile.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from kg_common import get_logger, get_settings
from kg_extractors.gliner import (
    DEFAULT_MODEL,
    DEFAULT_THRESHOLD,
    DOMAIN_LABELS,
    active_backend_name,
    compare_recall,
    extract_batch,
    gliner_available,
)

router = APIRouter(prefix="/api/v1/ml-ner", tags=["ml-ner"])

_log = get_logger("api.ml_ner")

DEFAULT_DEVICE = "cpu"


def _cfg() -> tuple[str, float, str]:
    """Read (model, threshold, device) from settings with §6.7 defaults."""
    s = get_settings()
    model = str(getattr(s, "gliner_model", DEFAULT_MODEL) or DEFAULT_MODEL)
    threshold = float(getattr(s, "gliner_threshold", DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD)
    device = str(getattr(s, "gliner_device", DEFAULT_DEVICE) or DEFAULT_DEVICE)
    return model, threshold, device


@router.get("/status")
def status() -> dict[str, Any]:
    """Report the live NER backend and its configuration (cheap; no model load)."""
    model, threshold, device = _cfg()
    available = gliner_available()
    backend = active_backend_name(model, device)
    return {
        "gliner_available": available,
        "backend": backend,
        "model": model if available else None,
        "device": device,
        "threshold": threshold,
        "labels": list(DOMAIN_LABELS),
        "note": (
            "Реальный GLiNER подключён — ML-NER поднимает recall над regex."
            if available
            else (
                "Пакет gliner не установлен: работает детерминированный "
                "rule-fallback (regex/словари). Установите `gliner` (torch+"
                "transformers) для ML-NER."
            )
        ),
    }


class ExtractRequest(BaseModel):
    """Ad-hoc NER request body."""

    text: str = Field(min_length=1, max_length=20_000)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    labels: list[str] | None = None


@router.post("/extract")
def extract(req: ExtractRequest) -> dict[str, Any]:
    """Run NER on a single passage; return anchored mentions + latency."""
    model, cfg_threshold, device = _cfg()
    threshold = req.threshold if req.threshold is not None else cfg_threshold
    labels = tuple(req.labels) if req.labels else DOMAIN_LABELS
    report = extract_batch(
        [req.text],
        model_name=model,
        threshold=threshold,
        labels=labels,
        device=device,
    )
    return {
        "backend": report.backend,
        "model": report.model,
        "threshold": threshold,
        "latency_ms": report.latency_ms,
        "n_mentions": report.n_mentions,
        "mentions": report.mentions[0] if report.mentions else [],
    }


def _corpus_chunks(store: Any, limit: int) -> list[dict[str, Any]]:
    """Read real chunk texts from the live graph (``:Node {label:'Chunk'}``)."""
    # Over-fetch, then keep only substantive chunks (length filtered in Python to
    # avoid Neo4j's deprecated size()-on-string).
    rows = store.rows(
        "MATCH (c:Node) WHERE c.label = 'Chunk' AND c.text IS NOT NULL AND c.text <> '' "
        "RETURN c.id, coalesce(c.text,''), coalesce(c.page, -1) "
        "ORDER BY c.id LIMIT $scan",
        {"scan": int(limit) * 6},
    )
    out: list[dict[str, Any]] = []
    for cid, text, page in rows:
        body = str(text or "")
        if len(body) <= 40:
            continue
        out.append(
            {
                "chunk_id": cid,
                "text": body,
                "page": int(page) if page not in (None, -1) else None,
            }
        )
        if len(out) >= int(limit):
            break
    return out


@router.get("/corpus")
def corpus(
    limit: int = Query(default=12, ge=1, le=64),
    threshold: float | None = Query(default=None, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Batched NER over live chunks + recall lift vs the regex/rule baseline.

    Pulls up to ``limit`` real ``Chunk`` texts from Neo4j, runs the active ML
    backend and the rule baseline on the same chunks, and returns per-chunk
    mentions plus the aggregate uplift ML gives over regex (§6.7 «why»).
    """
    model, cfg_threshold, device = _cfg()
    thr = threshold if threshold is not None else cfg_threshold
    store = get_store()
    chunks = _corpus_chunks(store, limit)

    if not chunks:
        return {
            "backend": active_backend_name(model, device),
            "model": model if gliner_available() else None,
            "threshold": thr,
            "chunks": [],
            "summary": {
                "n_chunks": 0,
                "rule_mentions": 0,
                "ml_mentions": 0,
                "lift": 0,
                "lift_pct": 0.0,
                "latency_ms": 0.0,
            },
            "note": "В графе нет чанков с текстом (label:'Chunk').",
        }

    texts = [c["text"] for c in chunks]
    cmp = compare_recall(
        texts, model_name=model, threshold=thr, device=device
    )
    per_chunk = cmp.get("ml_per_chunk", [])
    enriched = []
    for idx, chunk in enumerate(chunks):
        mentions = per_chunk[idx] if idx < len(per_chunk) else []
        enriched.append(
            {
                "chunk_id": chunk["chunk_id"],
                "page": chunk["page"],
                "text": chunk["text"],
                "mentions": mentions,
                "n_mentions": len(mentions),
            }
        )

    return {
        "backend": cmp["backend"],
        "model": cmp["model"],
        "threshold": thr,
        "chunks": enriched,
        "summary": {
            "n_chunks": cmp["n_chunks"],
            "rule_mentions": cmp["rule_mentions"],
            "ml_mentions": cmp["ml_mentions"],
            "lift": cmp["lift"],
            "lift_pct": cmp["lift_pct"],
            "latency_ms": cmp["latency_ms"],
        },
        "labels": list(DOMAIN_LABELS),
    }
