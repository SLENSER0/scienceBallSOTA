"""§17.13 — Evidence Inspector: single-evidence trust-field view-model.

Проецирует ВСЕ trust-поля §5.2.6 одного узла ``:Evidence`` в компактную,
неизменяемую вью-модель для «инспектора эвиденса» (*evidence inspector*, §17.13):
идентификатор документа/страница, локатор внутри страницы (таблица/рисунок/
параграф), извлечённое утверждение и сниппет, разобранный объект, экстрактор и
версия модели, уверенность, статус ревью и ревьюер, ссылка на ребро-источник, а
также навигация prev/next среди «сиблингов» — эвиденсов, разделяющих одно ребро.

English: :func:`build_evidence_inspector` reads one ``:Evidence`` node from a
:class:`~kg_retrievers.graph_store.KuzuGraphStore` and rolls every §5.2.6 trust
field into a frozen :class:`EvidenceInspectorView`. Prev/next ids are derived from
the position of ``evidence_id`` inside ``sibling_ids`` (evidence sharing the same
graph edge); a missing node yields ``None``.

Kuzu note: custom node props are not queryable columns, so the node is read whole
through :meth:`KuzuGraphStore.get_node` (which merges the ``props`` JSON) and every
non-base field (``locator`` parts, ``extracted_statement``, ``snippet``,
``parsed_object``, ``extractor``, ``model_version``, ``reviewer``, ``edge_ref``) is
read from that dict. Pure, deterministic, offline-safe (no LLM).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kg_retrievers.graph_store import KuzuGraphStore

# Метка узла-эвиденса в дженерик-таблице Node (§3). Evidence node label.
EVIDENCE_LABEL: str = "Evidence"

# Статус ревью по умолчанию, когда поле не задано (§5.2.6). Default review status.
DEFAULT_REVIEW_STATUS: str = "pending"


@dataclass(frozen=True)
class EvidenceInspectorView:
    """Trust-поля §5.2.6 одного эвиденса + навигация prev/next (§17.13).

    Attributes:
        evidence_id: идентификатор узла ``:Evidence``.
        doc_id: документ-источник (``None`` если неизвестен).
        page: номер страницы (int) или ``None``.
        locator: ``{tableId, figureId, paragraphId}`` — где на странице (значения
            могут быть ``None``).
        extracted_statement: извлечённое естественно-языковое утверждение.
        snippet: исходный сниппет текста.
        parsed_object: структурированный разбор (dict) или ``None``.
        extractor: имя/идентификатор экстрактора.
        model_version: версия модели-экстрактора.
        confidence: числовая уверенность (float) или ``None``.
        review_status: статус ревью (по умолчанию ``"pending"``).
        reviewer: кто ревьюил (``None`` если не ревьюилось).
        edge_ref: ссылка на ребро-источник (сгенерированный edge id) или ``None``.
        prev_id: предыдущий сиблинг в том же ребре или ``None``.
        next_id: следующий сиблинг в том же ребре или ``None``.
    """

    evidence_id: str
    doc_id: str | None
    page: int | None
    locator: dict[str, Any]
    extracted_statement: str | None
    snippet: str | None
    parsed_object: dict[str, Any] | None
    extractor: str | None
    model_version: str | None
    confidence: float | None
    review_status: str
    reviewer: str | None
    edge_ref: str | None
    prev_id: str | None
    next_id: str | None

    def as_dict(self) -> dict[str, Any]:
        """Сериализация в plain-JSON-совместимый dict с camelCase-ключами."""
        return {
            "evidenceId": self.evidence_id,
            "docId": self.doc_id,
            "page": self.page,
            "locator": dict(self.locator),
            "extractedStatement": self.extracted_statement,
            "snippet": self.snippet,
            "parsedObject": dict(self.parsed_object) if self.parsed_object is not None else None,
            "extractor": self.extractor,
            "modelVersion": self.model_version,
            "confidence": self.confidence,
            "reviewStatus": self.review_status,
            "reviewer": self.reviewer,
            "edgeRef": self.edge_ref,
            "prevId": self.prev_id,
            "nextId": self.next_id,
        }


def _opt_str(node: dict[str, Any], key: str) -> str | None:
    """Строковое поле узла (trim) или ``None``, если пусто/отсутствует."""
    raw = node.get(key)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _opt_int(node: dict[str, Any], key: str) -> int | None:
    """Целочисленное поле узла или ``None`` (bool отбрасывается)."""
    raw = node.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return int(raw)


def _opt_float(node: dict[str, Any], key: str) -> float | None:
    """Числовое поле узла в float или ``None`` (bool отбрасывается)."""
    raw = node.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _opt_dict(node: dict[str, Any], key: str) -> dict[str, Any] | None:
    """dict-поле узла или ``None``, если это не отображение."""
    raw = node.get(key)
    return dict(raw) if isinstance(raw, dict) else None


def _review_status(node: dict[str, Any]) -> str:
    """``review_status`` узла (trim) или дефолт ``"pending"``, если пусто."""
    raw = node.get("review_status")
    if raw is None:
        return DEFAULT_REVIEW_STATUS
    status = str(raw).strip()
    return status or DEFAULT_REVIEW_STATUS


def _prev_next(evidence_id: str, sibling_ids: list[str] | None) -> tuple[str | None, str | None]:
    """prev/next id по позиции ``evidence_id`` внутри ``sibling_ids``.

    ``None``/``None``, если сиблинги не заданы или ``evidence_id`` в них не найден.
    """
    if not sibling_ids or evidence_id not in sibling_ids:
        return None, None
    idx = sibling_ids.index(evidence_id)
    prev_id = sibling_ids[idx - 1] if idx > 0 else None
    next_id = sibling_ids[idx + 1] if idx < len(sibling_ids) - 1 else None
    return prev_id, next_id


def build_evidence_inspector(
    store: KuzuGraphStore,
    evidence_id: str,
    sibling_ids: list[str] | None = None,
) -> EvidenceInspectorView | None:
    """Собрать §17.13-вью-модель trust-полей одного эвиденса.

    Читает узел целиком через :meth:`KuzuGraphStore.get_node` (мерж ``props``),
    затем проецирует все §5.2.6-поля. Локатор — ``{tableId, figureId,
    paragraphId}``. prev/next вычисляются из позиции ``evidence_id`` в
    ``sibling_ids`` (эвиденсы одного ребра). Возвращает ``None``, если узла нет.
    """
    node = store.get_node(evidence_id)
    if node is None:
        return None

    locator: dict[str, Any] = {
        "tableId": _opt_str(node, "table_id"),
        "figureId": _opt_str(node, "figure_id"),
        "paragraphId": _opt_str(node, "paragraph_id"),
    }
    prev_id, next_id = _prev_next(evidence_id, sibling_ids)

    return EvidenceInspectorView(
        evidence_id=evidence_id,
        doc_id=_opt_str(node, "doc_id"),
        page=_opt_int(node, "page"),
        locator=locator,
        extracted_statement=_opt_str(node, "extracted_statement"),
        snippet=_opt_str(node, "snippet"),
        parsed_object=_opt_dict(node, "parsed_object"),
        extractor=_opt_str(node, "extractor"),
        model_version=_opt_str(node, "model_version"),
        confidence=_opt_float(node, "confidence"),
        review_status=_review_status(node),
        reviewer=_opt_str(node, "reviewer"),
        edge_ref=_opt_str(node, "edge_ref"),
        prev_id=prev_id,
        next_id=next_id,
    )
