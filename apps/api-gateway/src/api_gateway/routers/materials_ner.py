"""Materials-science domain NER + MatSciBERT embeddings, fused with GLiNER (§6.8).

Exposes the process-cached materials extractors (``kg_extractors.materials_ner``)
as four read-only endpoints so the UI can prove that a *materials-specialised*
NER stack — MatEntityRecognition fused with the §6.7 GLiNER extractor, plus
MatSciBERT sentence embeddings — is driving higher recall on materials /
properties / processes than either extractor alone:

* ``GET  /api/v1/materials-ner/status``  — which backends are live (real
  MatSciBERT / MatEntityRecognition vs the deterministic fallbacks), model ids,
  the §8.1 domain labels and the MatEntityRecognition tag map.
* ``POST /api/v1/materials-ner/fuse``    — run GLiNER ⊕ MatEntityRecognition on
  ad-hoc text; returns anchored fused mentions with per-mention provenance
  (which extractor(s) found it) + latency + agreement count.
* ``POST /api/v1/materials-ner/embed``   — MatSciBERT-embed a batch of texts;
  returns the vector dimension (hidden_size) and per-text L2 norm.
* ``GET  /api/v1/materials-ner/corpus``  — pull real ``Chunk`` texts from the
  live Neo4j graph, run fusion over the batch, and report the **recall lift**
  fusion gives over GLiNER alone (the "graph gets denser" signal).

The router only reads: it never mutates the graph. It works today on both the
embedded and the server (Neo4j :8000) profile; when OSS weights are unavailable
it honestly reports the deterministic fallback backends.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from kg_common import get_logger, get_settings
from kg_extractors.gliner import DOMAIN_LABELS
from kg_extractors.materials_ner import (
    DEFAULT_MATSCIBERT,
    MAT_TAG_MAP,
    MATERIALS_LABELS,
    MATSCIBERT_HIDDEN,
    fuse_text,
    get_embedder,
    get_mat_recognizer,
    mat_entity_available,
    transformers_available,
)

router = APIRouter(prefix="/api/v1/materials-ner", tags=["materials-ner"])

_log = get_logger("api.materials_ner")

DEFAULT_DEVICE = "cpu"
DEFAULT_THRESHOLD = 0.5


def _cfg() -> tuple[str, float, str]:
    """Read (matscibert_model, gliner_threshold, device) from settings + defaults."""
    s = get_settings()
    model = str(getattr(s, "matscibert_model", DEFAULT_MATSCIBERT) or DEFAULT_MATSCIBERT)
    threshold = float(getattr(s, "gliner_threshold", DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD)
    device = str(getattr(s, "gliner_device", DEFAULT_DEVICE) or DEFAULT_DEVICE)
    return model, threshold, device


@router.get("/status")
def status() -> dict[str, Any]:
    """Report the live materials NER / embedding backends (cheap; no model load)."""
    model, threshold, device = _cfg()
    tf_ok = transformers_available()
    mat_ok = mat_entity_available()
    recognizer = get_mat_recognizer(device)
    return {
        "matscibert_available": tf_ok,
        "matscibert_model": model if tf_ok else None,
        "matscibert_hidden": MATSCIBERT_HIDDEN,
        "mat_entity_available": mat_ok,
        "mat_entity_backend": recognizer.backend,
        "device": device,
        "threshold": threshold,
        "domain_labels": list(DOMAIN_LABELS),
        "materials_labels": list(MATERIALS_LABELS),
        "tag_map": dict(MAT_TAG_MAP),
        "note": (
            "Материаловедческий NER (MatEntityRecognition) в fusion с GLiNER "
            "поднимает recall на материалах/свойствах/процессах."
            if (tf_ok or mat_ok)
            else (
                "OSS-веса MatSciBERT/MatEntityRecognition не установлены: работают "
                "детерминированные fallback'и (лексикон + hash-эмбеддинги той же "
                "размерности). Установите transformers+torch и вендор "
                "MatEntityRecognition для полного ML-режима."
            )
        ),
    }


class FuseRequest(BaseModel):
    """Ad-hoc fusion request body."""

    text: str = Field(min_length=1, max_length=20_000)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


@router.post("/fuse")
def fuse(req: FuseRequest) -> dict[str, Any]:
    """Run GLiNER ⊕ MatEntityRecognition fusion on a passage; anchored mentions."""
    _, cfg_threshold, device = _cfg()
    threshold = req.threshold if req.threshold is not None else cfg_threshold
    report = fuse_text(
        req.text,
        threshold=threshold,
        iou_threshold=req.iou_threshold,
        device=device,
    )
    out = report.as_dict()
    out["threshold"] = threshold
    out["iou_threshold"] = req.iou_threshold
    return out


class EmbedRequest(BaseModel):
    """Batched MatSciBERT embedding request body."""

    texts: list[str] = Field(min_length=1, max_length=64)
    include_vectors: bool = False


@router.post("/embed")
def embed(req: EmbedRequest) -> dict[str, Any]:
    """MatSciBERT-embed a batch of texts; report the vector dimension + norms."""
    model, _, device = _cfg()
    embedder = get_embedder(model, device)
    report = embedder.embed_batch(req.texts)
    norms = [round(sum(v * v for v in vec) ** 0.5, 4) for vec in report.vectors]
    out = report.as_dict(include_vectors=req.include_vectors)
    out["norms"] = norms
    out["hidden_size"] = MATSCIBERT_HIDDEN
    return out


def _corpus_chunks(store: Any, limit: int) -> list[dict[str, Any]]:
    """Read real chunk texts from the live graph (``:Node {label:'Chunk'}``)."""
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
    limit: int = Query(default=10, ge=1, le=48),
    threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    iou_threshold: float = Query(default=0.5, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Batched fusion over live chunks + recall lift vs GLiNER alone (§6.8 «why»).

    Pulls up to ``limit`` real ``Chunk`` texts from Neo4j, runs the fused
    GLiNER ⊕ MatEntityRecognition stack per chunk, and reports per-chunk fused
    mentions plus the aggregate uplift fusion gives over GLiNER on its own.
    """
    _, cfg_threshold, device = _cfg()
    thr = threshold if threshold is not None else cfg_threshold
    store = get_store()
    chunks = _corpus_chunks(store, limit)

    empty_summary = {
        "n_chunks": 0,
        "gliner_mentions": 0,
        "mat_mentions": 0,
        "fused_mentions": 0,
        "agreement": 0,
        "lift": 0,
        "lift_pct": 0.0,
        "latency_ms": 0.0,
    }
    if not chunks:
        recognizer = get_mat_recognizer(device)
        return {
            "gliner_backend": "rule",
            "mat_backend": recognizer.backend,
            "threshold": thr,
            "iou_threshold": iou_threshold,
            "chunks": [],
            "summary": empty_summary,
            "note": "В графе нет чанков с текстом (label:'Chunk').",
        }

    enriched: list[dict[str, Any]] = []
    tot_gliner = tot_mat = tot_fused = tot_agree = 0
    tot_latency = 0.0
    gliner_backend = "rule"
    mat_backend = "lexicon-fallback"
    for chunk in chunks:
        rep = fuse_text(
            chunk["text"], threshold=thr, iou_threshold=iou_threshold, device=device
        )
        gliner_backend = rep.gliner_backend
        mat_backend = rep.mat_backend
        tot_gliner += rep.n_gliner
        tot_mat += rep.n_mat
        tot_fused += rep.n_fused
        tot_agree += rep.n_agreement
        tot_latency += rep.latency_ms
        enriched.append(
            {
                "chunk_id": chunk["chunk_id"],
                "page": chunk["page"],
                "text": chunk["text"],
                "mentions": rep.mentions,
                "n_gliner": rep.n_gliner,
                "n_mat": rep.n_mat,
                "n_fused": rep.n_fused,
                "n_agreement": rep.n_agreement,
            }
        )

    # Lift = how many extra distinct mentions fusion surfaces over GLiNER alone.
    lift = tot_fused - tot_gliner
    lift_pct = round(100.0 * lift / tot_gliner, 1) if tot_gliner else 0.0
    return {
        "gliner_backend": gliner_backend,
        "mat_backend": mat_backend,
        "threshold": thr,
        "iou_threshold": iou_threshold,
        "chunks": enriched,
        "summary": {
            "n_chunks": len(chunks),
            "gliner_mentions": tot_gliner,
            "mat_mentions": tot_mat,
            "fused_mentions": tot_fused,
            "agreement": tot_agree,
            "lift": lift,
            "lift_pct": lift_pct,
            "latency_ms": round(tot_latency, 2),
        },
        "domain_labels": list(DOMAIN_LABELS),
    }
