"""Expert feedback loop → regression cases (§23.22).

Domain-expert validation loop: an expert flags an answer as ``useful`` /
``wrong_number`` / ``missing_evidence`` (plus ``not_useful`` / ``bad_graph`` /
``bad_entity_match``). Каждое событие сохраняется как ``FeedbackEvent`` с привязкой
к answer/run/evidence (provenance §3.7), а КАЖДАЯ ошибка (не ``useful``)
замораживается в детерминированный ``RegressionCase`` и попадает в regression-набор
для §18.11 (``kg_eval.regression_gate`` уже готов). Так пользовательская ошибка
превращается в regression-тест — цикл улучшения качества на реальных оценках.

Вся дистилляция «фидбэк → регрессионный кейс» переиспользована из
:mod:`kg_eval.feedback_regression_case` (``from_feedback`` + ``dedup``) — роутер
только ведёт хранилище событий, считает экспертные метрики (§23.22: scientific
usefulness / time-to-evidence / clicks-to-verify / trust score) и публикует
замороженный набор кейсов рядом с историей §18.11.

Хранилище (append-only, под живой server-профиль):

* ``<artifacts>/feedback/events.jsonl``            — сырые FeedbackEvent'ы.
* ``<artifacts>/eval/feedback_regression/cases.json`` — дедуплицированный набор
  RegressionCase (снапшот для §18.11).

Эндпоинты:

* ``POST /api/v1/expert-feedback/submit`` — записать событие → (при ошибке) кейс.
* ``GET  /api/v1/expert-feedback/events`` — лента событий, новые сверху.
* ``GET  /api/v1/expert-feedback/cases``  — замороженный regression-набор.
* ``GET  /api/v1/expert-feedback/stats``  — экспертные метрики + acceptance §23.22.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway.auth import current_role, current_user
from kg_eval.feedback_regression_case import RegressionCase, dedup, from_feedback

router = APIRouter(prefix="/api/v1/expert-feedback", tags=["expert-feedback"])

# Feedback verdicts. Only ``useful`` counts as a positive review; everything
# else is an expert-flagged error that is frozen into a regression case.
_POSITIVE = "useful"
_TYPES = frozenset(
    {
        "useful",
        "not_useful",
        "wrong_number",
        "missing_evidence",
        "bad_graph",
        "bad_entity_match",
    }
)

# §23.22 acceptance: ≥30 expert-reviewed answers, ≥80% useful/trustworthy.
_MIN_REVIEWS = 30
_MIN_USEFUL_RATE = 0.80


# --- Persistence -------------------------------------------------------------


def _feedback_dir() -> Path:
    """``<artifacts_dir>/feedback`` — created on demand (idempotent)."""
    from kg_common import get_settings

    root = Path(get_settings().artifacts_dir) / "feedback"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cases_dir() -> Path:
    """``<artifacts_dir>/eval/feedback_regression`` — the §18.11-consumable set."""
    from kg_common import get_settings

    root = Path(get_settings().artifacts_dir) / "eval" / "feedback_regression"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _events_path() -> Path:
    return _feedback_dir() / "events.jsonl"


def _load_events() -> list[dict[str, Any]]:
    """All stored FeedbackEvents in write order (oldest-first). Corrupt lines skipped."""
    path = _events_path()
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def _append_event(event: dict[str, Any]) -> None:
    with _events_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _regression_cases(events: list[dict[str, Any]]) -> tuple[RegressionCase, ...]:
    """Distil error events into a deduplicated frozen regression set.

    Только события-ошибки (``type != 'useful'``) дают кейс; безопасно вызываем
    ``from_feedback`` (обязательные поля гарантированы валидацией при submit).
    """
    cases: list[RegressionCase] = []
    for ev in events:
        if str(ev.get("type", "")) == _POSITIVE:
            continue
        try:
            cases.append(from_feedback(ev))
        except Exception:
            # Malformed historical event — never let it break the snapshot.
            continue
    return dedup(cases)


def _publish_cases(cases: tuple[RegressionCase, ...]) -> str | None:
    """Persist the deduplicated regression set as a JSON snapshot for §18.11."""
    try:
        path = _cases_dir() / "cases.json"
        payload = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "count": len(cases),
            "source": "expert_feedback",
            "cases": [c.as_dict() for c in cases],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        return str(path)
    except Exception:
        return None


# --- Request models ----------------------------------------------------------


class FeedbackRequest(BaseModel):
    """One expert verdict on an answer (§23.22 feedback-controls)."""

    type: str = Field(..., description="useful | not_useful | wrong_number | missing_evidence | "
                                       "bad_graph | bad_entity_match")
    question: str = Field(..., min_length=1, description="The question the answer responded to")
    answer: str = Field(default="", description="Answer text under review (optional)")
    run_id: str = Field(default="", description="Provenance: agent run id (§3.7)")
    evidence_id: str = Field(default="", description="Provenance: evidence/node id under review")
    # wrong_number specifics — required for that type.
    wrong_value: str = Field(default="", description="The wrong value the answer gave")
    correct_value: str = Field(default="", description="The value a correct answer must contain")
    # missing_evidence specifics.
    expected_evidence: str = Field(default="", description="Evidence a correct answer must cite")
    note: str = Field(default="", description="Free-text expert remark")
    # §23.22 scientific/trust metrics (optional, client-measured).
    time_to_evidence_ms: float | None = Field(default=None, ge=0)
    clicks_to_verify: int | None = Field(default=None, ge=0)


# --- Endpoints ---------------------------------------------------------------


@router.post("/submit")
def submit(
    req: FeedbackRequest,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict[str, Any]:
    """Record a FeedbackEvent and (on any error) freeze a regression case (§23.22).

    ``useful`` — положительный отзыв, кейс не создаётся. Любой другой тип — ошибка:
    событие превращается в детерминированный regression-кейс, дедуплицируется и
    попадает в набор для §18.11. Возвращает событие, созданный кейс (если есть) и
    обновлённый размер regression-набора.
    """
    fb_type = req.type.strip()
    if fb_type not in _TYPES:
        raise HTTPException(status_code=400, detail=f"unknown feedback type: {req.type!r}")
    if fb_type == "wrong_number" and not (req.wrong_value and req.correct_value):
        raise HTTPException(
            status_code=400,
            detail="wrong_number feedback requires both wrong_value and correct_value",
        )

    event: dict[str, Any] = {
        "id": "fb-" + uuid.uuid4().hex[:12],
        "type": fb_type,
        "question": req.question.strip(),
        "answer": req.answer,
        "run_id": req.run_id,
        "evidence_id": req.evidence_id,
        "note": req.note,
        "role": role,
        "user": user,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if fb_type == "wrong_number":
        event["wrong_value"] = req.wrong_value
        event["correct_value"] = req.correct_value
    if fb_type == "missing_evidence" and req.expected_evidence:
        event["expected_evidence"] = req.expected_evidence
    if req.time_to_evidence_ms is not None:
        event["time_to_evidence_ms"] = req.time_to_evidence_ms
    if req.clicks_to_verify is not None:
        event["clicks_to_verify"] = req.clicks_to_verify

    _append_event(event)

    # Rebuild + publish the frozen regression set from the full event history.
    events = _load_events()
    cases = _regression_cases(events)
    snapshot_path = _publish_cases(cases)

    regression_case: dict[str, Any] | None = None
    if fb_type != _POSITIVE:
        try:
            regression_case = from_feedback(event).as_dict()
        except Exception:
            regression_case = None

    return {
        "event": event,
        "regression_case": regression_case,
        "created_regression_case": regression_case is not None,
        "regression_set_size": len(cases),
        "snapshot_path": snapshot_path,
    }


@router.get("/events")
def events(limit: int = 50) -> dict[str, Any]:
    """FeedbackEvent feed, newest-first (default 50)."""
    all_events = _load_events()
    ordered = list(reversed(all_events))[: max(1, limit)]
    return {"total": len(all_events), "count": len(ordered), "events": ordered}


@router.get("/cases")
def cases() -> dict[str, Any]:
    """The deduplicated frozen regression set fed into §18.11."""
    cases_ = _regression_cases(_load_events())
    return {"count": len(cases_), "cases": [c.as_dict() for c in cases_]}


@router.get("/stats")
def stats() -> dict[str, Any]:
    """Expert quality metrics + §23.22 acceptance status.

    Считает: разбивку по типам, useful-rate (trust score), средние scientific-
    метрики (time-to-evidence, clicks-to-verify), размер regression-набора и
    выполнение критерия приёмки (≥30 reviewed, ≥80% useful).
    """
    events_ = _load_events()
    total = len(events_)
    by_type: dict[str, int] = dict.fromkeys(_TYPES, 0)
    tte: list[float] = []
    clicks: list[int] = []
    for ev in events_:
        t = str(ev.get("type", ""))
        if t in by_type:
            by_type[t] += 1
        if isinstance(ev.get("time_to_evidence_ms"), (int, float)):
            tte.append(float(ev["time_to_evidence_ms"]))
        if isinstance(ev.get("clicks_to_verify"), int):
            clicks.append(int(ev["clicks_to_verify"]))

    useful = by_type.get(_POSITIVE, 0)
    errors = total - useful
    useful_rate = round(useful / total, 4) if total else 0.0
    reg_set = _regression_cases(events_)

    acceptance = {
        "min_reviews": _MIN_REVIEWS,
        "min_useful_rate": _MIN_USEFUL_RATE,
        "reviews_ok": total >= _MIN_REVIEWS,
        "useful_rate_ok": useful_rate >= _MIN_USEFUL_RATE,
        "met": total >= _MIN_REVIEWS and useful_rate >= _MIN_USEFUL_RATE,
    }

    return {
        "total": total,
        "useful": useful,
        "errors": errors,
        "useful_rate": useful_rate,
        "trust_score": useful_rate,
        "by_type": by_type,
        "regression_set_size": len(reg_set),
        "avg_time_to_evidence_ms": round(sum(tte) / len(tte), 2) if tte else None,
        "avg_clicks_to_verify": round(sum(clicks) / len(clicks), 2) if clicks else None,
        "acceptance": acceptance,
    }
