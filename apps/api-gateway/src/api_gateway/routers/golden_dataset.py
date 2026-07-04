"""Read-only API over the §18.6 golden QA dataset (corpus + quota gate).

Экспонирует уже собранный и провалидированный золотой набор §15.1/§18.6
(``packages/kg_eval/datasets/golden/*.yaml``) через живой server-профиль (Neo4j
:8000): версия манифеста (semver), отчёт валидатора (точное покрытие квот
20/15/10/10/10/10, уникальность ``id``, наличие эталонного Al-Cu примера), разбивка
по категориям и языкам (ru/en), а также сами вопросы с полями ``expected_*``.

Вся загрузка/валидация переиспользована из уже готового
:mod:`kg_eval.datasets` (loader + validator + Pydantic-схема) — роутер только
собирает срез, фильтрует и отдаёт JSON, НИЧЕГО не пересчитывая заново и не
редактируя данные. Данных графа он не трогает (это статический корпус вопросов).

Эндпоинты:

* ``GET /api/v1/golden-dataset/summary``      — манифест + сводка валидатора + разбивки.
* ``GET /api/v1/golden-dataset/validate``     — полный отчёт валидатора (CI-гейт §18.6).
* ``GET /api/v1/golden-dataset/questions``    — список вопросов (фильтры category/language/q).
* ``GET /api/v1/golden-dataset/questions/{qid}`` — один вопрос со всеми ``expected_*``.
* ``GET /api/v1/golden-dataset/reference``    — эталонный Al-Cu пример (§15.1) целиком.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from kg_eval.datasets import (
    REFERENCE_ID,
    GoldenQuestion,
    load_golden,
    load_manifest,
    validate_golden,
)
from kg_eval.golden_quota import REQUIRED_QUOTAS

router = APIRouter(prefix="/api/v1/golden-dataset", tags=["golden-dataset"])


# --- Corpus access (cached; the dataset is static YAML on disk) --------------


@lru_cache(maxsize=1)
def _questions() -> tuple[GoldenQuestion, ...]:
    """All schema-validated golden questions, sorted by (category, id).

    Кэшируется на процесс: корпус — статические YAML, живого пересчёта не нужно.
    Ошибки схемы/дублей ``id`` поднимаются как есть из :func:`load_golden`.
    """
    return tuple(load_golden())


def _question_dict(q: GoldenQuestion) -> dict[str, Any]:
    """Full JSON view of one question (Pydantic → plain dict, enums as values)."""
    return q.model_dump(mode="json")


def _summary_row(q: GoldenQuestion) -> dict[str, Any]:
    """Compact row for list views (no heavy expected_* payloads)."""
    return {
        "id": q.id,
        "category": q.category.value,
        "language": q.language.value,
        "question": q.question,
        "has_numeric": q.expected_numeric is not None,
        "has_citations": not q.expected_citations.is_empty(),
        "n_entities": len(q.expected_entities.flat()),
        "n_gaps": len(q.expected_gaps),
        "n_contradictions": len(q.expected_contradictions),
        "tags": list(q.tags),
    }


# --- Endpoints ---------------------------------------------------------------


@router.get("/summary")
def summary() -> dict[str, Any]:
    """Manifest + validator verdict + per-category / per-language breakdown (§18.6).

    Отдаёт всё, что нужно дашборду одним запросом: версию набора, вердикт
    валидатора (``ok`` + покрытие квот), таблицу «квота vs факт» по 6 категориям
    §15.1 и двуязычную разбивку (ru/en).
    """
    try:
        manifest = load_manifest()
        report = validate_golden()
        questions = _questions()
    except Exception as exc:  # surfaced verbatim so the gate reason is visible
        raise HTTPException(status_code=500, detail=f"golden dataset load failed: {exc}") from exc

    lang_counts = Counter(q.language.value for q in questions)
    quota_rows = [
        {
            "category": cat,
            "quota": quota,
            "count": report.quota.counts.get(cat, 0),
            "met": report.quota.counts.get(cat, 0) >= quota,
            "surplus": max(0, report.quota.counts.get(cat, 0) - quota),
        }
        for cat, quota in REQUIRED_QUOTAS.items()
    ]

    return {
        "manifest": {
            "dataset_version": manifest.dataset_version,
            "name": manifest.name,
            "description": manifest.description,
            "git_tag": manifest.git_tag,
        },
        "total": report.total,
        "ok": report.ok,
        "reference_present": report.reference_present,
        "reference_id": REFERENCE_ID,
        "quota": quota_rows,
        "languages": dict(sorted(lang_counts.items())),
        "warnings": list(report.warnings),
        "schema_errors": list(report.schema_errors),
        "duplicate_ids": list(report.duplicate_ids),
    }


@router.get("/validate")
def validate() -> dict[str, Any]:
    """Full machine-readable validator report — CI acceptance gate (§18.6).

    ``ok`` истинно ⇔ нет ошибок схемы, нет дублей ``id``, точное покрытие квот
    (нет недобора и перебора) и присутствует эталонный Al-Cu пример.
    """
    try:
        return validate_golden().as_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"validation failed: {exc}") from exc


@router.get("/questions")
def questions(
    category: str | None = Query(default=None, description="Filter by §15.1 category"),
    language: str | None = Query(default=None, description="Filter by language (ru/en)"),
    q: str | None = Query(default=None, description="Substring match on question text"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Filtered, paged list of golden questions (compact rows) (§18.6)."""
    if category is not None and category not in REQUIRED_QUOTAS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown category {category!r}; expected one of {sorted(REQUIRED_QUOTAS)}",
        )
    needle = q.strip().lower() if q else None
    rows = [
        item
        for item in _questions()
        if (category is None or item.category.value == category)
        and (language is None or item.language.value == language)
        and (needle is None or needle in item.question.lower())
    ]
    page = rows[offset : offset + limit]
    return {
        "total_matched": len(rows),
        "returned": len(page),
        "offset": offset,
        "limit": limit,
        "questions": [_summary_row(item) for item in page],
    }


@router.get("/questions/{qid}")
def question_detail(qid: str) -> dict[str, Any]:
    """One golden question with all ``expected_*`` fields (§15.1); 404 if unknown."""
    for item in _questions():
        if item.id == qid:
            return _question_dict(item)
    raise HTTPException(status_code=404, detail=f"golden question {qid!r} not found")


@router.get("/reference")
def reference() -> dict[str, Any]:
    """Canonical Al-Cu 2024 / aging 180C 2h / hardness reference example (§15.1).

    Единый эталонный пример, на который опираются метрики доверия и gate
    «0 unsupported claims». 404 (с явной причиной), если он вдруг отсутствует.
    """
    for item in _questions():
        if item.id == REFERENCE_ID:
            return _question_dict(item)
    raise HTTPException(
        status_code=404,
        detail=f"reference example {REFERENCE_ID!r} missing from golden dataset",
    )
