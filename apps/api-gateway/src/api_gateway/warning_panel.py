"""§17.7 unified answer warning-panel aggregator (§5.2.2 «warning panel»).

Guardrails уже метят отдельные сигналы (числовые claims без цитат — §13.12
:func:`agent_service.answer_validator.validate_answer`; contradictions/gaps —
поля :class:`kg_common.dto.AnswerPayload`), но нет ОДНОЙ панели рисков ответа с
переходами к деталям. Этот модуль — чистая, детерминированная проекция уже
готового :class:`AnswerPayload` в четыре категории предупреждений:

* **contradictions** — где литература спорит (→ экран «Противоречия»);
* **low_confidence** — узлы/рёбра/цитаты с ``confidence`` строго ниже порога
  (→ экран «Сущности» / evidence);
* **missing_data** — пробелы типа ``missing_*`` (→ экран «Пробелы и риски»);
* **unsupported_claims** — числовые утверждения без inline-цитаты ``[n]``
  (→ Evidence Inspector), взятые из уже готового §13.12 валидатора.

Каждый item несёт ``detail_ref`` (``view`` + ``anchor``) — куда прыгнуть в UI.
Ничего не трогает граф-стор и не зовёт LLM: вход — уже собранный ответ.
Reuses, а не переписывает: :func:`agent_service.answer_validator.validate_answer`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common.dto import AnswerPayload

__all__ = ["WarningItem", "WarningCategory", "WarningPanel", "build_warning_panel"]

# Порядок серьёзности (больше = серьёзнее) для сведе́ния общего severity.
_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_RANK_SEVERITY = {v: k for k, v in _SEVERITY_RANK.items()}

# Фиксированный severity каждой категории (общий severity = максимум по непустым).
_CATEGORY_SEVERITY = {
    "unsupported_claims": "critical",  # guardrail-breach: число без evidence (Phase 5 = 0)
    "contradictions": "high",  # литература спорит — требует арбитража
    "low_confidence": "medium",  # ниже порога уверенности
    "missing_data": "medium",  # пробел в данных
}

_CATEGORY_LABELS = {
    "contradictions": ("Противоречия", "Contradictions"),
    "low_confidence": ("Низкая уверенность", "Low confidence"),
    "missing_data": ("Нет данных (пробелы)", "Missing data"),
    "unsupported_claims": ("Числа без цитат", "Unsupported claims"),
}

# Куда ведёт «перейти к деталям» — id View во фронтенде (store.ts).
_CATEGORY_VIEW = {
    "contradictions": "contradictions",
    "low_confidence": "entities",
    "missing_data": "gaps",
    "unsupported_claims": "evidence",
}


@dataclass(frozen=True)
class WarningItem:
    """Одна карточка предупреждения с ссылкой на детали (§17.7)."""

    title: str
    detail: str
    detail_ref: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"title": self.title, "detail": self.detail, "detail_ref": self.detail_ref}


@dataclass(frozen=True)
class WarningCategory:
    """Категория предупреждений с её счётчиком, severity и items (§17.7)."""

    key: str
    label_ru: str
    label_en: str
    severity: str
    count: int
    items: tuple[WarningItem, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label_ru": self.label_ru,
            "label_en": self.label_en,
            "severity": self.severity,
            "count": self.count,
            "items": [it.as_dict() for it in self.items],
        }


@dataclass(frozen=True)
class WarningPanel:
    """Единая панель рисков ответа: 4 категории + сводка (§17.7 / §5.2.2)."""

    severity: str
    has_warnings: bool
    total: int
    counts: dict[str, int]
    categories: tuple[WarningCategory, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "has_warnings": self.has_warnings,
            "total": self.total,
            "counts": self.counts,
            "categories": [c.as_dict() for c in self.categories],
        }


def _gap_type(gap: dict[str, Any]) -> str:
    """Тип gap-а под обе конвенции ключей (``type`` / ``gap_type``)."""
    for key in ("gap_type", "type"):
        val = gap.get(key)
        if isinstance(val, str):
            return val
    return ""


def _is_low_conf(value: Any, threshold: float) -> bool:
    """True, если ``value`` — число (не bool) строго меньше порога."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and float(value) < threshold
    )


def _label(item: dict[str, Any], *keys: str, fallback: str) -> str:
    """Первое непустое строковое поле из ``keys`` (иначе ``fallback``)."""
    for key in keys:
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _contradiction_items(answer: AnswerPayload) -> list[WarningItem]:
    out: list[WarningItem] = []
    for i, c in enumerate(answer.contradictions):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or c.get("contradiction_id") or i)
        title = _label(c, "name", "subject", "property", fallback=f"противоречие {cid}")
        spread = c.get("spread") or c.get("values") or c.get("conflict")
        detail = (
            f"Расхождение значений: {spread}" if spread else "Литература расходится в значениях"
        )
        out.append(
            WarningItem(
                title=title,
                detail=detail,
                detail_ref={"view": _CATEGORY_VIEW["contradictions"], "anchor": cid},
            )
        )
    return out


def _missing_data_items(answer: AnswerPayload) -> list[WarningItem]:
    out: list[WarningItem] = []
    for i, g in enumerate(answer.gaps):
        if not isinstance(g, dict):
            continue
        gtype = _gap_type(g)
        if not gtype.startswith("missing_"):
            continue
        gid = str(g.get("id") or g.get("gap_id") or i)
        title = _label(g, "name", "subject", "title", fallback=gtype)
        detail = _label(
            g,
            "description_ru",
            "description",
            "explanation",
            fallback=f"Пробел типа «{gtype}» — нет данных",
        )
        out.append(
            WarningItem(
                title=title,
                detail=detail,
                detail_ref={"view": _CATEGORY_VIEW["missing_data"], "anchor": gid},
            )
        )
    return out


def _low_confidence_items(answer: AnswerPayload, threshold: float) -> list[WarningItem]:
    out: list[WarningItem] = []
    view = _CATEGORY_VIEW["low_confidence"]

    thr = f"{threshold:.2f}"
    if answer.graph is not None:
        for node in answer.graph.nodes:
            if _is_low_conf(node.confidence, threshold):
                conf = f"{float(node.confidence):.2f}"
                out.append(
                    WarningItem(
                        title=f"{node.label} ({node.type})",
                        detail=f"Уверенность узла {conf} < порога {thr}",
                        detail_ref={"view": view, "anchor": node.id},
                    )
                )
        for edge in answer.graph.edges:
            if _is_low_conf(edge.confidence, threshold):
                conf = f"{float(edge.confidence):.2f}"
                out.append(
                    WarningItem(
                        title=f"связь {edge.label}",
                        detail=f"Уверенность связи {conf} < порога {thr}",
                        detail_ref={"view": view, "anchor": edge.id},
                    )
                )

    for cit in answer.citations:
        conf = cit.evidence.confidence
        if _is_low_conf(conf, threshold):
            out.append(
                WarningItem(
                    title=f"цитата {cit.marker}",
                    detail=f"Уверенность источника {float(conf):.2f} < порога {thr}",
                    detail_ref={
                        "view": _CATEGORY_VIEW["unsupported_claims"],
                        "anchor": cit.evidence.evidence_id,
                    },
                )
            )
    return out


def _unsupported_items(answer: AnswerPayload) -> list[WarningItem]:
    # Reuse the shipped §13.12 numeric-claim guardrail — не переписываем.
    from agent_service.answer_validator import validate_answer

    validation = validate_answer(answer.answer_markdown, list(answer.citations))
    out: list[WarningItem] = []
    for i, num in enumerate(validation.numeric_claims_without_evidence):
        out.append(
            WarningItem(
                title=f"«{num}» без ссылки",
                detail="Числовое утверждение в ответе не привязано к inline-цитате [n]",
                detail_ref={"view": _CATEGORY_VIEW["unsupported_claims"], "anchor": f"claim-{i}"},
            )
        )
    return out


def _make_category(key: str, items: list[WarningItem]) -> WarningCategory:
    ru, en = _CATEGORY_LABELS[key]
    severity = _CATEGORY_SEVERITY[key] if items else "none"
    return WarningCategory(
        key=key,
        label_ru=ru,
        label_en=en,
        severity=severity,
        count=len(items),
        items=tuple(items),
    )


def build_warning_panel(
    answer: AnswerPayload, *, low_confidence_threshold: float = 0.5
) -> WarningPanel:
    """Свести :class:`AnswerPayload` в единую панель предупреждений (§17.7).

    :param answer: уже собранный ответ агента (markdown + citations + gaps +
        contradictions + graph).
    :param low_confidence_threshold: узел/ребро/цитата считаются low-confidence
        при ``confidence`` СТРОГО меньше порога.
    :returns: :class:`WarningPanel` с 4 категориями и сводным severity.
    """
    categories = [
        _make_category("contradictions", _contradiction_items(answer)),
        _make_category("unsupported_claims", _unsupported_items(answer)),
        _make_category("low_confidence", _low_confidence_items(answer, low_confidence_threshold)),
        _make_category("missing_data", _missing_data_items(answer)),
    ]

    counts = {c.key: c.count for c in categories}
    total = sum(counts.values())

    max_rank = max(
        (_SEVERITY_RANK[c.severity] for c in categories if c.count > 0),
        default=_SEVERITY_RANK["none"],
    )
    overall = _RANK_SEVERITY[max_rank]

    return WarningPanel(
        severity=overall,
        has_warnings=total > 0,
        total=total,
        counts=counts,
        categories=tuple(categories),
    )
