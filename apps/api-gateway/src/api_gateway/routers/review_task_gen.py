"""Авто-генерация review-задач по 6 правилам над ЖИВЫМ графом (§16.5).

Очередь курирования не должна наполняться вручную: те же сигналы, что pipeline
уже посчитал при извлечении (уверенность, флаги качества, ER-вердикты,
противоречия, отсутствие критических полей, неизвестные термины), достаточны,
чтобы *отчеканить* задачу проверки. Этот модуль реализует шесть чистых правил
(§16.5) поверх активного store (server-профиль Neo4j :8000 / embedded Kuzu) с
единым интерфейсом :class:`Rule` (``detect(context) -> list[ReviewTaskDraft]``),
дедупликацией (§16.4) и приоритизацией (§16.4), и отдаёт их через ручной
re-scan endpoint (без полного реингеста).

Шесть правил (§16.5):

* ``low_confidence``        — evidence/факт с ``confidence < threshold`` (по
  умолчанию ``0.65``, синхронно с §6.2 ``min_confidence``); маршрутизация
  переиспользует :func:`kg_extractors.review_routing.route_extraction` (§6.15);
* ``ambiguous_er``          — ER-выход ``decision:"review_needed"`` либо малый
  margin top-1/top-2 (переиспользует :func:`kg_er.resolve`, как §8.8);
* ``contradiction``         — ребро ``CONTRADICTS`` или узел ``Contradiction``
  (§8.2, Phase 7);
* ``missing_critical_field``— у ``Measurement``/``ProcessingRegime``/``Experiment``
  нет critical-поля (список per-label в config, согласован с §11-гэпами);
* ``low_quality_ocr``       — evidence из низкокачественного OCR
  (``source_type=table_cell`` с низкой уверенностью либо ``ocr_score`` ниже
  порога, §5);
* ``new_schema_term``       — термин/label вне controlled-vocabulary
  (переиспользует :func:`kg_extractors.property_normalize.normalize_property` и
  ``kg_schema`` ``NODE_LABELS``), ``target_type=schema`` (§12.1).

Каждое правило чистое и юнит-тестируемое: оно читает граф только на чтение через
``store.rows(...)`` и не пишет ничего — повторный прогон над теми же данными даёт
те же черновики, а дедупликация по ``dedup_key`` гарантирует идемпотентность
(§16.5 acceptance «повторный прогон создаёт 0 новых задач»). Отключение любого
правила в запросе убирает соответствующие задачи.

Эндпоинты:

* ``POST /api/v1/curation/tasks/scan`` — прогнать все включённые правила
  (опц. scope по ``doc_id``/``batch_id``, override порогов, список ``disabled``)
  и вернуть дедуплицированную очередь черновиков.
* ``GET  /api/v1/curation/tasks/rules`` — каталог правил + активная конфигурация.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/curation/tasks", tags=["curation"])

# --- task types (§16.2 ReviewTask.task_type) ---------------------------------
TASK_LOW_CONFIDENCE = "low_confidence"
TASK_AMBIGUOUS_ER = "ambiguous_er"
TASK_CONTRADICTION = "contradiction"
TASK_MISSING_CRITICAL_FIELD = "missing_critical_field"
TASK_LOW_QUALITY_OCR = "low_quality_ocr"
TASK_NEW_SCHEMA_TERM = "new_schema_term"

#: Все шесть типов задач в каноническом порядке (для каталога правил).
ALL_TASK_TYPES: tuple[str, ...] = (
    TASK_LOW_CONFIDENCE,
    TASK_AMBIGUOUS_ER,
    TASK_CONTRADICTION,
    TASK_MISSING_CRITICAL_FIELD,
    TASK_LOW_QUALITY_OCR,
    TASK_NEW_SCHEMA_TERM,
)

#: Ранг важности типа (§16.4): contradiction > missing_critical_field >
#: ambiguous_er > low_confidence > low_quality_ocr > new_schema_term.
TYPE_RANK: dict[str, int] = {
    TASK_CONTRADICTION: 6,
    TASK_MISSING_CRITICAL_FIELD: 5,
    TASK_AMBIGUOUS_ER: 4,
    TASK_LOW_CONFIDENCE: 3,
    TASK_LOW_QUALITY_OCR: 2,
    TASK_NEW_SCHEMA_TERM: 1,
}

# --- default configuration (§16.5, all overridable per request) --------------
#: Порог уверенности для ``low_confidence`` (§6.2 ``min_confidence``).
DEFAULT_CONFIDENCE_THRESHOLD = 0.65
#: Порог OCR-скора для ``low_quality_ocr`` (ниже → в очередь).
DEFAULT_OCR_THRESHOLD = 0.6
#: Минимальный margin top-1/top-2 в ER; ниже → ``ambiguous_er`` даже без review_needed.
DEFAULT_ER_MARGIN = 0.15

#: Critical-поля per-label (§16.5, согласованы с §11 gap-типами). Значение —
#: список требований: ``prop:<name>`` (свойство узла) или ``edge:<TYPE>`` (ребро).
DEFAULT_CRITICAL_FIELDS: dict[str, list[str]] = {
    "Measurement": ["prop:value_normalized", "prop:normalized_unit"],
    "ProcessingRegime": ["prop:temperature_c", "prop:time_h"],
    "Experiment": ["edge:USED_EQUIPMENT"],
}

#: Метки узлов, на которых имеет смысл проверять уверенность (§16.5 low_confidence).
_FACTUAL_LABELS: tuple[str, ...] = (
    "Claim",
    "Finding",
    "KnowledgeClaim",
    "Measurement",
    "Recommendation",
)
#: Типы сущностей, по которым гоняем ER (как в §8.8 er_candidates).
_ER_TYPES: tuple[str, ...] = ("Material", "TechnologySolution", "Equipment", "Method")

_MAX_ROWS = 500  # cap на выборку каждого правила (защита от гигантских графов)
_PRIORITY_DECIMALS = 6


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReviewTaskDraft:
    """Один черновик review-задачи, отчеканенный правилом (§16.5 / §16.2).

    Поля соответствуют модели ``ReviewTask`` (§16.2): ``task_type``,
    ``target_type``, ``target_id``, ``payload``, вычисленный ``priority`` (§16.4)
    и стабильный ``dedup_key`` (§16.4) для идемпотентности.
    """

    task_type: str
    target_type: str
    target_id: str
    payload: dict[str, Any]
    priority: float
    dedup_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "payload": self.payload,
            "priority": self.priority,
            "dedup_key": self.dedup_key,
        }


@dataclass(frozen=True)
class RuleContext:
    """Вход правила (§16.5): store на чтение + scope + пороги + critical-поля.

    ``store`` обязан реализовывать ``rows(cypher, params) -> list[list]``.
    Правила только читают граф, поэтому любой fake-store с ``rows`` делает их
    юнит-тестируемыми без БД.
    """

    store: Any
    doc_id: str | None = None
    batch_id: str | None = None
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    ocr_threshold: float = DEFAULT_OCR_THRESHOLD
    er_margin: float = DEFAULT_ER_MARGIN
    critical_fields: dict[str, list[str]] = field(
        default_factory=lambda: dict(DEFAULT_CRITICAL_FIELDS)
    )

    def rows(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        try:
            return list(self.store.rows(cypher, params or {}))
        except Exception:  # правило деградирует до пустого, а не роняет scan
            return []


@dataclass(frozen=True)
class Rule:
    """Правило генерации: тип задачи + чистая функция ``detect(context)`` (§16.5)."""

    task_type: str
    title: str
    detect: Callable[[RuleContext], list[ReviewTaskDraft]]


# ---------------------------------------------------------------------------
# Priority & dedup (§16.4)
# ---------------------------------------------------------------------------
def compute_priority(
    task_type: str,
    *,
    confidence: float = 1.0,
    evidence_count: int = 0,
    centrality: int = 0,
) -> float:
    """Приоритет задачи (§16.4): функция типа, уверенности, evidence и центральности.

    Ранг типа доминирует (умножен на 10, диапазон 10..60), внутри типа задача
    тем выше, чем ниже ``confidence`` (``1-conf``), чем больше связанного
    ``evidence`` и выше ``centrality`` (degree узла). Итог округлён до 6 знаков.
    """
    base = 10.0 * TYPE_RANK.get(task_type, 1)
    conf_term = 1.0 - _clamp01(confidence)
    ev_term = 0.1 * min(max(evidence_count, 0), 10)
    cen_term = 0.05 * min(max(centrality, 0), 20)
    return round(base + conf_term + ev_term + cen_term, _PRIORITY_DECIMALS)


def _clamp01(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def make_dedup_key(task_type: str, target_type: str, target_id: str, payload_sig: str = "") -> str:
    """Стабильный ``dedup_key`` (§16.4): sha1 от типа/цели/подписи payload.

    Одна открытая задача на (тип, цель) при пустой подписи; ``payload_sig``
    различает несколько задач одного типа на одной цели (например, разные наборы
    missing-полей), сохраняя идемпотентность повторного прогона.
    """
    raw = "|".join([task_type, target_type, str(target_id), payload_sig])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"rev:{digest}"


def _to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return default
    return default


def _snippet(text: Any, limit: int = 200) -> str:
    s = str(text or "").strip().replace("\n", " ")
    return s[:limit]


# ---------------------------------------------------------------------------
# Rule 1 — low_confidence (§16.5)
# ---------------------------------------------------------------------------
def detect_low_confidence(ctx: RuleContext) -> list[ReviewTaskDraft]:
    """Задачи по evidence/фактам с ``confidence < threshold`` (§16.5).

    Каждый кандидат прогоняется через :func:`route_extraction` (§6.15) — задача
    ставится только если роутер тоже требует ревью; ``priority`` растёт с падением
    уверенности. payload: ``evidence_id``/``target_id``, ``confidence``,
    ``threshold``, ``text``-snippet.
    """
    from kg_extractors.review_routing import ACTION_REVIEW, route_extraction

    thr = ctx.confidence_threshold
    scope, params = _doc_scope(ctx, "e")
    labels = ["Evidence", *_FACTUAL_LABELS]
    params.update({"labels": labels, "thr": thr, "cap": _MAX_ROWS})
    cypher = (
        "MATCH (e:Node) WHERE e.label IN $labels "
        "AND e.confidence IS NOT NULL AND e.confidence < $thr "
        f"{scope}"
        "RETURN e.id, e.label, e.confidence, coalesce(e.text, e.name, ''), "
        "coalesce(e.source_type,''), coalesce(e.doc_id,'') "
        "ORDER BY e.confidence ASC LIMIT $cap"
    )
    drafts: list[ReviewTaskDraft] = []
    for row in ctx.rows(cypher, params):
        tid, label, conf, text, source_type, doc_id = row
        decision = route_extraction(
            {"confidence": conf, "source_type": source_type},
            thresholds={"auto_accept_at": max(thr, 0.85), "reject_at": 0.0},
        )
        if decision.action != ACTION_REVIEW:
            continue
        target_type = "evidence" if label == "Evidence" else "node"
        payload = {
            "evidence_id": str(tid),
            "label": str(label),
            "confidence": round(float(conf), 4),
            "threshold": thr,
            "text": _snippet(text),
            "doc_id": str(doc_id) or None,
            "router_reasons": list(decision.reasons),
        }
        drafts.append(
            ReviewTaskDraft(
                task_type=TASK_LOW_CONFIDENCE,
                target_type=target_type,
                target_id=str(tid),
                payload=payload,
                priority=compute_priority(TASK_LOW_CONFIDENCE, confidence=float(conf)),
                dedup_key=make_dedup_key(TASK_LOW_CONFIDENCE, target_type, str(tid)),
            )
        )
    return drafts


# ---------------------------------------------------------------------------
# Rule 2 — ambiguous_er (§16.5)
# ---------------------------------------------------------------------------
def _mention_rows(ctx: RuleContext, entity_type: str) -> list[dict[str, Any]]:
    """Канонические узлы *entity_type* как ER-mentions (как §8.8 er_candidates)."""
    rows = ctx.rows(
        "MATCH (n:Node) WHERE n.label = $label "
        "RETURN n.id, coalesce(n.name, n.canonical_name, ''), coalesce(n.formula,''), "
        "coalesce(n.review_status,'') LIMIT $cap",
        {"label": entity_type, "cap": _MAX_ROWS},
    )
    out: list[dict[str, Any]] = []
    for nid, name, formula, review_status in rows:
        out.append(
            {
                "unique_id": str(nid),
                "name": str(name),
                "formula": str(formula) or None,
                "_label": entity_type,
                "_review_status": str(review_status) or None,
            }
        )
    return out


def detect_ambiguous_er(ctx: RuleContext) -> list[ReviewTaskDraft]:
    """Задачи по ER-выходу ``decision:"review_needed"`` либо малому margin (§16.5).

    Переиспользует :func:`kg_er.resolve` (§8.8) над каноническими узлами каждого
    поддерживаемого типа. Черновик ставится, если предложение имеет вердикт
    ``review_needed`` или его ``match_probability`` в «серой» зоне margin. payload:
    ``candidate_id``, ``mentions``, ``match_probability``, предлагаемый canonical.
    """
    try:
        from kg_er import resolve  # ленивый heavy Splink/duckdb import
    except Exception:
        return []

    drafts: list[ReviewTaskDraft] = []
    lo, hi = 0.5 - ctx.er_margin, 0.5 + ctx.er_margin
    for entity_type in _ER_TYPES:
        mentions = _mention_rows(ctx, entity_type)
        if len(mentions) < 2:
            continue
        reviewed = frozenset(
            m["unique_id"] for m in mentions if m.get("_review_status") in {"accepted", "corrected"}
        )
        try:
            result = resolve(entity_type, mentions, reviewed_ids=reviewed)
            proposals = result.proposals
        except Exception:  # ER не должен ронять scan
            continue
        by_id = {m["unique_id"]: m for m in mentions}
        for p in proposals:
            prob = float(p.probability)
            review_needed = p.decision.value == "review_needed"
            ambiguous_margin = lo <= prob <= hi
            if not (review_needed or ambiguous_margin):
                continue
            candidate_id = f"ercand:{entity_type}:{'+'.join(sorted(p.members))}"
            members = [
                {"id": mid, "name": by_id.get(mid, {}).get("name")} for mid in p.members
            ]
            payload = {
                "candidate_id": candidate_id,
                "entity_type": entity_type,
                "decision": p.decision.value,
                "match_probability": round(prob, 4),
                "canonical_id": p.canonical_id,
                "reason": "review_needed" if review_needed else "low_margin",
                "mentions": members,
            }
            drafts.append(
                ReviewTaskDraft(
                    task_type=TASK_AMBIGUOUS_ER,
                    target_type="entity",
                    target_id=candidate_id,
                    payload=payload,
                    # confidence = |prob-0.5| нормировано: чем ближе к 0.5, тем выше приоритет
                    priority=compute_priority(
                        TASK_AMBIGUOUS_ER,
                        confidence=abs(prob - 0.5) * 2.0,
                        evidence_count=len(p.members),
                    ),
                    dedup_key=make_dedup_key(TASK_AMBIGUOUS_ER, "entity", candidate_id),
                )
            )
    return drafts


# ---------------------------------------------------------------------------
# Rule 3 — contradiction (§16.5)
# ---------------------------------------------------------------------------
def detect_contradiction(ctx: RuleContext) -> list[ReviewTaskDraft]:
    """Задачи по ``CONTRADICTS``-рёбрам и узлам ``Contradiction`` (§16.5 / §8.2).

    payload содержит оба ``claim_id``, конфликтующие значения/единицы и
    ``contradiction_id``. Пары нормализуются (сортировка id), чтобы направление
    ребра не плодило дублей.
    """
    drafts: list[ReviewTaskDraft] = []
    seen: set[str] = set()

    # (a) прямые CONTRADICTS-рёбра между claim/measurement.
    # value_normalized (DOUBLE) и name (STRING) читаем раздельно — Kuzu не
    # coalesce-ит разнотипные выражения; значение собираем в Python.
    edge_rows = ctx.rows(
        "MATCH (a:Node)-[r:Rel {type:'CONTRADICTS'}]->(b:Node) "
        "RETURN a.id, a.value_normalized, coalesce(a.name,''), coalesce(a.normalized_unit,''), "
        "b.id, b.value_normalized, coalesce(b.name,''), coalesce(b.normalized_unit,''), "
        "coalesce(r.confidence, 0.0) LIMIT $cap",
        {"cap": _MAX_ROWS},
    )
    for row in edge_rows:
        a_id, a_val, a_name, a_unit, b_id, b_val, b_name, b_unit, conf = row
        pair = tuple(sorted((str(a_id), str(b_id))))
        contradiction_id = f"contra:{pair[0]}~{pair[1]}"
        if contradiction_id in seen:
            continue
        seen.add(contradiction_id)
        payload = {
            "contradiction_id": contradiction_id,
            "claim_a": {
                "id": str(a_id),
                "value": _jsonable(a_val if a_val is not None else a_name),
                "unit": str(a_unit) or None,
            },
            "claim_b": {
                "id": str(b_id),
                "value": _jsonable(b_val if b_val is not None else b_name),
                "unit": str(b_unit) or None,
            },
            "edge_confidence": round(_to_float(conf), 4),
        }
        drafts.append(
            ReviewTaskDraft(
                task_type=TASK_CONTRADICTION,
                target_type="edge",
                target_id=contradiction_id,
                payload=payload,
                priority=compute_priority(TASK_CONTRADICTION, confidence=0.0),
                dedup_key=make_dedup_key(TASK_CONTRADICTION, "edge", contradiction_id),
            )
        )

    # (b) явные узлы Contradiction (§8.1) ещё не помеченные resolved
    node_rows = ctx.rows(
        "MATCH (c:Node) WHERE c.label = 'Contradiction' "
        "AND coalesce(c.status,'') <> 'resolved' "
        "RETURN c.id, coalesce(c.name,'') LIMIT $cap",
        {"cap": _MAX_ROWS},
    )
    for cid, name in node_rows:
        target = str(cid)
        if target in seen:
            continue
        seen.add(target)
        drafts.append(
            ReviewTaskDraft(
                task_type=TASK_CONTRADICTION,
                target_type="node",
                target_id=target,
                payload={"contradiction_id": target, "name": str(name)},
                priority=compute_priority(TASK_CONTRADICTION, confidence=0.0),
                dedup_key=make_dedup_key(TASK_CONTRADICTION, "node", target),
            )
        )
    return drafts


def _jsonable(value: Any) -> Any:
    if isinstance(value, (int, float, str)) or value is None:
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Rule 4 — missing_critical_field (§16.5)
# ---------------------------------------------------------------------------
def detect_missing_critical_field(ctx: RuleContext) -> list[ReviewTaskDraft]:
    """Задачи по узлам без critical-полей (§16.5, согласовано с §11-гэпами).

    Для каждой метки из ``critical_fields`` проверяется наличие требуемых свойств
    (``prop:<name>``) и рёбер (``edge:<TYPE>``); payload перечисляет ``missing_fields``.
    ``dedup_key`` учитывает набор недостающих полей (подпись payload).
    """
    drafts: list[ReviewTaskDraft] = []
    for label, requirements in ctx.critical_fields.items():
        prop_reqs = [r.split(":", 1)[1] for r in requirements if r.startswith("prop:")]
        edge_reqs = [r.split(":", 1)[1] for r in requirements if r.startswith("edge:")]
        rows = ctx.rows(
            "MATCH (n:Node) WHERE n.label = $label RETURN n LIMIT $cap",
            {"label": label, "cap": _MAX_ROWS},
        )
        for (node,) in rows:
            props = node if isinstance(node, dict) else {}
            nid = str(props.get("id", ""))
            if not nid:
                continue
            missing = [f for f in prop_reqs if _is_blank(props.get(f))]
            for etype in edge_reqs:
                if not _has_out_edge(ctx, nid, etype):
                    missing.append(f"edge:{etype}")
            if not missing:
                continue
            missing_sorted = sorted(missing)
            payload = {
                "label": label,
                "missing_fields": missing_sorted,
                "name": str(props.get("name", "")),
            }
            drafts.append(
                ReviewTaskDraft(
                    task_type=TASK_MISSING_CRITICAL_FIELD,
                    target_type="node",
                    target_id=nid,
                    payload=payload,
                    priority=compute_priority(
                        TASK_MISSING_CRITICAL_FIELD,
                        confidence=_to_float(props.get("confidence"), 1.0),
                        evidence_count=len(missing_sorted),
                    ),
                    dedup_key=make_dedup_key(
                        TASK_MISSING_CRITICAL_FIELD, "node", nid, ",".join(missing_sorted)
                    ),
                )
            )
    return drafts


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _has_out_edge(ctx: RuleContext, node_id: str, edge_type: str) -> bool:
    rows = ctx.rows(
        "MATCH (n:Node {id:$id})-[:Rel {type:$t}]->() RETURN count(*) LIMIT 1",
        {"id": node_id, "t": edge_type},
    )
    return bool(rows) and int(rows[0][0]) > 0


# ---------------------------------------------------------------------------
# Rule 5 — low_quality_ocr (§16.5)
# ---------------------------------------------------------------------------
def detect_low_quality_ocr(ctx: RuleContext) -> list[ReviewTaskDraft]:
    """Задачи по evidence из низкокачественного OCR (§16.5 / §5).

    Триггерит на ``ocr_score`` ниже порога ЛИБО ``source_type=table_cell`` с
    низкой уверенностью распознавания. payload: ``doc_id``, ``page``, ``ocr_score``.
    """
    thr = ctx.ocr_threshold
    scope, params = _doc_scope(ctx, "e")
    params.update({"thr": thr, "cap": _MAX_ROWS})
    cypher = (
        "MATCH (e:Node) WHERE e.label = 'Evidence' AND ("
        "(e.ocr_score IS NOT NULL AND e.ocr_score < $thr) "
        "OR (coalesce(e.source_type,'') = 'table_cell' "
        "AND coalesce(e.confidence, 1.0) < $thr)) "
        f"{scope}"
        "RETURN e.id, coalesce(e.doc_id,''), e.page, e.ocr_score, "
        "coalesce(e.source_type,''), coalesce(e.confidence, 1.0), "
        "coalesce(e.text,'') LIMIT $cap"
    )
    drafts: list[ReviewTaskDraft] = []
    for row in ctx.rows(cypher, params):
        eid, doc_id, page, ocr_score, source_type, conf, text = row
        score = _to_float(ocr_score, _to_float(conf, 1.0))
        payload = {
            "doc_id": str(doc_id) or None,
            "page": int(page) if isinstance(page, (int, float)) else page,
            "ocr_score": round(score, 4),
            "source_type": str(source_type) or None,
            "text": _snippet(text),
        }
        drafts.append(
            ReviewTaskDraft(
                task_type=TASK_LOW_QUALITY_OCR,
                target_type="evidence",
                target_id=str(eid),
                payload=payload,
                priority=compute_priority(TASK_LOW_QUALITY_OCR, confidence=score),
                dedup_key=make_dedup_key(TASK_LOW_QUALITY_OCR, "evidence", str(eid)),
            )
        )
    return drafts


# ---------------------------------------------------------------------------
# Rule 6 — new_schema_term (§16.5 / §12.1)
# ---------------------------------------------------------------------------
def detect_new_schema_term(ctx: RuleContext) -> list[ReviewTaskDraft]:
    """Задачи по терминам вне controlled-vocabulary (§16.5 / §12.1).

    Неизвестные ``property_name`` детектируются через
    :func:`kg_extractors.property_normalize.normalize_property` (``None`` = вне
    словаря), неизвестные метки узлов — сверкой с ``kg_schema`` ``NODE_LABELS``.
    payload содержит термин, контекст и предложение маппинга; ``target_type=schema``.
    """
    from kg_extractors.property_normalize import normalize_property

    node_labels = _canonical_labels()
    drafts: list[ReviewTaskDraft] = []

    # (a) неизвестные property_name
    prop_rows = ctx.rows(
        "MATCH (n:Node) WHERE n.property_name IS NOT NULL AND n.property_name <> '' "
        "RETURN DISTINCT n.property_name, count(*) LIMIT $cap",
        {"cap": _MAX_ROWS},
    )
    for term, cnt in prop_rows:
        surface = str(term).strip()
        if not surface:
            continue
        try:
            norm = normalize_property(surface)
        except Exception:
            norm = None
        if norm is not None:
            continue  # уже в словаре
        drafts.append(
            _schema_draft(
                term=surface,
                kind="property",
                occurrences=int(cnt),
                context=f"property_name '{surface}' вне controlled-vocabulary (§12.1)",
                mapping_suggestion=None,
            )
        )

    # (b) неизвестные метки узлов
    if node_labels:
        label_rows = ctx.rows(
            "MATCH (n:Node) WHERE n.label IS NOT NULL "
            "RETURN DISTINCT n.label, count(*) LIMIT $cap",
            {"cap": _MAX_ROWS},
        )
        for label, cnt in label_rows:
            name = str(label).strip()
            if not name or name in node_labels:
                continue
            drafts.append(
                _schema_draft(
                    term=name,
                    kind="label",
                    occurrences=int(cnt),
                    context=f"node label '{name}' вне LinkML-схемы (§8.2)",
                    mapping_suggestion=None,
                )
            )
    return drafts


def _canonical_labels() -> frozenset[str]:
    """Канонические метки узлов из LinkML-схемы (§8.2); пусто при недоступности."""
    try:
        from kg_schema.schema_reachability import NODE_LABELS

        return frozenset(str(x) for x in NODE_LABELS)
    except Exception:
        return frozenset()


def _schema_draft(
    *, term: str, kind: str, occurrences: int, context: str, mapping_suggestion: str | None
) -> ReviewTaskDraft:
    payload = {
        "term": term,
        "term_kind": kind,
        "occurrences": occurrences,
        "context": context,
        "mapping_suggestion": mapping_suggestion,
    }
    return ReviewTaskDraft(
        task_type=TASK_NEW_SCHEMA_TERM,
        target_type="schema",
        target_id=f"schema:{kind}:{term}",
        payload=payload,
        priority=compute_priority(TASK_NEW_SCHEMA_TERM, confidence=1.0, evidence_count=occurrences),
        dedup_key=make_dedup_key(TASK_NEW_SCHEMA_TERM, "schema", f"{kind}:{term}"),
    )


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------
def _doc_scope(ctx: RuleContext, var: str) -> tuple[str, dict[str, Any]]:
    """Опциональный scope-фрагмент по ``doc_id``/``batch_id`` для evidence-запроса."""
    params: dict[str, Any] = {}
    clause = ""
    if ctx.doc_id:
        params["doc_id"] = ctx.doc_id
        clause += f"AND coalesce({var}.doc_id,'') = $doc_id "
    if ctx.batch_id:
        params["batch_id"] = ctx.batch_id
        clause += f"AND coalesce({var}.batch_id,'') = $batch_id "
    return clause, params


# ---------------------------------------------------------------------------
# Rule registry & orchestrator (§16.5)
# ---------------------------------------------------------------------------
RULES: tuple[Rule, ...] = (
    Rule(TASK_LOW_CONFIDENCE, "Низкая уверенность", detect_low_confidence),
    Rule(TASK_AMBIGUOUS_ER, "Неоднозначное разрешение сущности", detect_ambiguous_er),
    Rule(TASK_CONTRADICTION, "Противоречие", detect_contradiction),
    Rule(TASK_MISSING_CRITICAL_FIELD, "Нет критического поля", detect_missing_critical_field),
    Rule(TASK_LOW_QUALITY_OCR, "Низкое качество OCR", detect_low_quality_ocr),
    Rule(TASK_NEW_SCHEMA_TERM, "Новый термин схемы", detect_new_schema_term),
)

_RULES_BY_TYPE: dict[str, Rule] = {r.task_type: r for r in RULES}


def generate_tasks(
    ctx: RuleContext,
    *,
    disabled: frozenset[str] = frozenset(),
) -> list[ReviewTaskDraft]:
    """Прогнать все включённые правила, дедуплицировать и отсортировать (§16.5).

    Каждое правило ``r`` в :data:`RULES`, чей ``task_type`` не в *disabled*,
    вызывается на *ctx*; черновики с одинаковым ``dedup_key`` схлопываются в один
    (берётся самый приоритетный), а результат сортируется по убыванию ``priority``
    (§16.4). Повторный прогон над теми же данными даёт тот же набор ``dedup_key``
    → 0 новых задач при апсерте в очередь (идемпотентность §16.5).
    """
    kept: dict[str, tuple[int, ReviewTaskDraft]] = {}
    order = 0
    for rule in RULES:
        if rule.task_type in disabled:
            continue
        for draft in rule.detect(ctx):
            prev = kept.get(draft.dedup_key)
            if prev is None:
                kept[draft.dedup_key] = (order, draft)
                order += 1
            elif draft.priority > prev[1].priority:
                kept[draft.dedup_key] = (prev[0], draft)
    ranked = sorted(kept.values(), key=lambda pair: (-pair[1].priority, pair[0]))
    return [draft for _, draft in ranked]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class ScanRequest(BaseModel):
    doc_id: str | None = Field(default=None, description="Ограничить scope одним документом")
    batch_id: str | None = Field(default=None, description="Ограничить scope одним батчем")
    disabled_rules: list[str] = Field(
        default_factory=list, description="task_type правил, которые отключить"
    )
    confidence_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Override порога low_confidence (§6.2)"
    )
    ocr_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Override порога low_quality_ocr"
    )
    er_margin: float | None = Field(
        default=None, ge=0.0, le=0.5, description="Override margin ambiguous_er"
    )
    limit: int = Field(default=200, ge=1, le=1000, description="Максимум задач в ответе")


def _context_from(req: ScanRequest, store: Any) -> RuleContext:
    kwargs: dict[str, Any] = {"store": store, "doc_id": req.doc_id, "batch_id": req.batch_id}
    if req.confidence_threshold is not None:
        kwargs["confidence_threshold"] = req.confidence_threshold
    if req.ocr_threshold is not None:
        kwargs["ocr_threshold"] = req.ocr_threshold
    if req.er_margin is not None:
        kwargs["er_margin"] = req.er_margin
    return RuleContext(**kwargs)


@router.post("/scan")
def scan(req: ScanRequest, _role: str = Depends(current_role)) -> dict:
    """Ручной re-scan: прогнать 6 правил над графом → дедуплицированная очередь (§16.5).

    Без полного реингеста. ``disabled_rules`` убирает соответствующие задачи;
    пороги можно переопределить. Ответ содержит задачи (по убыванию приоритета),
    разбивку по типам и активную конфигурацию — для UI очереди курирования.
    """
    t0 = time.perf_counter()
    store = get_store()
    ctx = _context_from(req, store)
    disabled = frozenset(r for r in req.disabled_rules if r in _RULES_BY_TYPE)
    drafts = generate_tasks(ctx, disabled=disabled)

    by_type: dict[str, int] = dict.fromkeys(ALL_TASK_TYPES, 0)
    for d in drafts:
        by_type[d.task_type] = by_type.get(d.task_type, 0) + 1

    limited = drafts[: req.limit]
    return {
        "count": len(drafts),
        "returned": len(limited),
        "by_type": by_type,
        "disabled_rules": sorted(disabled),
        "scope": {"doc_id": req.doc_id, "batch_id": req.batch_id},
        "config": {
            "confidence_threshold": ctx.confidence_threshold,
            "ocr_threshold": ctx.ocr_threshold,
            "er_margin": ctx.er_margin,
        },
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "tasks": [d.as_dict() for d in limited],
    }


@router.get("/rules")
def rules() -> dict:
    """Каталог 6 правил (§16.5): тип, заголовок, ранг приоритета, дефолт-конфиг."""
    return {
        "rules": [
            {
                "task_type": r.task_type,
                "title": r.title,
                "type_rank": TYPE_RANK[r.task_type],
                "target_type": _default_target_type(r.task_type),
            }
            for r in RULES
        ],
        "defaults": {
            "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            "ocr_threshold": DEFAULT_OCR_THRESHOLD,
            "er_margin": DEFAULT_ER_MARGIN,
            "critical_fields": DEFAULT_CRITICAL_FIELDS,
        },
        "priority_order": list(ALL_TASK_TYPES),
    }


def _default_target_type(task_type: str) -> str:
    return {
        TASK_LOW_CONFIDENCE: "evidence",
        TASK_AMBIGUOUS_ER: "entity",
        TASK_CONTRADICTION: "edge",
        TASK_MISSING_CRITICAL_FIELD: "node",
        TASK_LOW_QUALITY_OCR: "evidence",
        TASK_NEW_SCHEMA_TERM: "schema",
    }.get(task_type, "node")


# Экспорт для юнит-тестов фикстурного датасета (§16.5 acceptance).
__all__ = [
    "ReviewTaskDraft",
    "RuleContext",
    "Rule",
    "RULES",
    "generate_tasks",
    "compute_priority",
    "make_dedup_key",
    "detect_low_confidence",
    "detect_ambiguous_er",
    "detect_contradiction",
    "detect_missing_critical_field",
    "detect_low_quality_ocr",
    "detect_new_schema_term",
]
