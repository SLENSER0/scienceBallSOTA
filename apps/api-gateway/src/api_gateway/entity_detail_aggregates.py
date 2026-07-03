"""Агрегаты карточки сущности для ``GET /entities/{id}`` (§14.5).

Роутер детали сущности собирает карточку из узла графа и его рёбер, но считает
агрегаты (счётчик доказательств, число связей, флаг верификации, уверенность,
статус ревью, недостающие поля) прямо в обработчике, без переиспользуемого
агрегатора. Здесь живёт эта чистая, детерминированная логика: узел и списки
входящих/исходящих рёбер отображаются в неизменяемый :class:`EntityAggregates`.
Свойства узла Kuzu не являются колонками запроса — их читают через ``get_node``,
поэтому агрегатор принимает уже прочитанный ``Mapping`` узла, а не строку курсора.

The entity-detail router builds its card from a graph node plus its edges, yet
computes the aggregates (evidence count, relation count, verified flag,
confidence, review status, missing fields) inline in the handler with no reusable
aggregator. This module owns that pure, deterministic logic: a node mapping and
its inbound/outbound edge lists collapse into a frozen :class:`EntityAggregates`.
Kuzu custom node props are not queryable columns — they are read via ``get_node``
— so the aggregator takes an already-materialised node ``Mapping``, not a row.

* :class:`EntityAggregates` — frozen aggregates with camelCase :meth:`as_dict`.
* :func:`compute_aggregates` — ``node`` + edges + required fields → aggregates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EntityAggregates",
    "compute_aggregates",
]


def _evidence_count(node: Mapping[str, Any]) -> int:
    """Число доказательств узла — из ``evidence_count`` или ``len(evidence)`` (§14.5).

    Предпочитается явное целое ``evidence_count``; иначе берётся длина списка
    ``evidence``; при отсутствии обоих — ``0``.

    Prefer an explicit integer ``evidence_count``; otherwise fall back to the
    length of an ``evidence`` list; default ``0`` when neither is present.
    """
    raw = node.get("evidence_count")
    if isinstance(raw, bool):  # bool — подкласс int, но не счётчик / not a count
        raw = None
    if isinstance(raw, int):
        return raw
    evidence = node.get("evidence")
    if isinstance(evidence, Sequence) and not isinstance(evidence, str | bytes):
        return len(evidence)
    return 0


def _missing_fields(node: Mapping[str, Any], required_fields: Sequence[str]) -> tuple[str, ...]:
    """Недостающие обязательные поля узла (§14.5).

    Поле считается недостающим, если оно отсутствует в узле либо его значение —
    ``None`` или пустая строка. Порядок повторяет ``required_fields``.

    A field is missing when it is absent from the node or its value is ``None``
    or an empty string. Order mirrors ``required_fields``.
    """
    missing: list[str] = []
    for field in required_fields:
        if field not in node:
            missing.append(field)
            continue
        value = node[field]
        if value is None or value == "":
            missing.append(field)
    return tuple(missing)


@dataclass(frozen=True, slots=True)
class EntityAggregates:
    """Неизменяемые агрегаты карточки сущности (§14.5).

    Immutable entity-detail aggregates. ``relation_count`` is the total of
    inbound and outbound edges; ``missing_fields`` lists required fields that are
    absent or empty on the node. :meth:`as_dict` emits camelCase keys per §5.3.
    """

    evidence_count: int
    relation_count: int
    verified: bool
    confidence: float
    review_status: str
    missing_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """camelCase-представление агрегатов для тела ответа (§5.3, §14.5).

        Ключи ``evidenceCount``/``relationCount``/``reviewStatus``/``missingFields``
        следуют соглашению §5.3; ``missingFields`` — список для JSON.

        camelCase view for the response body: ``evidenceCount``/``relationCount``/
        ``reviewStatus``/``missingFields`` follow §5.3; ``missingFields`` is a list
        for JSON serialisation.
        """
        return {
            "evidenceCount": self.evidence_count,
            "relationCount": self.relation_count,
            "verified": self.verified,
            "confidence": self.confidence,
            "reviewStatus": self.review_status,
            "missingFields": list(self.missing_fields),
        }


def compute_aggregates(
    node: Mapping[str, Any],
    in_edges: Sequence[Mapping[str, Any]],
    out_edges: Sequence[Mapping[str, Any]],
    *,
    required_fields: Sequence[str],
) -> EntityAggregates:
    """Свернуть узел и его рёбра в :class:`EntityAggregates` (§14.5).

    ``relation_count = len(in_edges) + len(out_edges)``. Флаг ``verified`` по
    умолчанию ``False``, ``confidence`` — ``0.0``, ``review_status`` —
    ``"unreviewed"``, если соответствующего свойства нет в узле. ``evidence_count``
    и ``missing_fields`` вычисляются вспомогательными функциями. Функция чистая и
    детерминированная, без побочных эффектов и обращений к хранилищу.

    Collapse a node and its edges into :class:`EntityAggregates`.
    ``relation_count = len(in_edges) + len(out_edges)``. ``verified`` defaults to
    ``False``, ``confidence`` to ``0.0`` and ``review_status`` to ``"unreviewed"``
    when the node lacks the property. ``evidence_count`` and ``missing_fields``
    come from the helpers above. Pure, deterministic, side-effect free.
    """
    return EntityAggregates(
        evidence_count=_evidence_count(node),
        relation_count=len(in_edges) + len(out_edges),
        verified=bool(node.get("verified", False)),
        confidence=float(node.get("confidence", 0.0)),
        review_status=str(node.get("review_status", "unreviewed")),
        missing_fields=_missing_fields(node, required_fields),
    )
