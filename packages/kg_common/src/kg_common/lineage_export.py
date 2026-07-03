"""OpenLineage-style RunEvent export helper (§10.5 lineage export).

Тонкая, дружественная обёртка над :mod:`kg_common.lineage_openlineage`
(§10.9) — a friendly, positional facade for emitting a single OpenLineage
``RunEvent`` JSON-документ БЕЗ сетевых зависимостей. Функция
:func:`lineage_event` принимает аргументы в удобном порядке
``(job, run_id, inputs, outputs)`` и делегирует построение конверта событию
:func:`~kg_common.lineage_openlineage.to_openlineage_event`; :func:`to_json`
даёт детерминированную (отсортированные ключи) сериализацию для файлового
экспорта / round-trip (§10.5 «экспорт происхождения прогона»).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from kg_common.lineage_openlineage import (
    DEFAULT_NAMESPACE,
    DEFAULT_PRODUCER,
    DatasetLike,
    to_openlineage_event,
)

#: Детерминированное значение ``eventTime`` по умолчанию (эпоха UTC).
#: Позволяет :func:`lineage_event` выдавать идентичный документ на равных
#: входах — задайте явный ``event_time`` для реального штампа времени (§10.5).
DEFAULT_EVENT_TIME = "1970-01-01T00:00:00Z"

#: Тип события по умолчанию — терминальное завершение прогона (OpenLineage).
DEFAULT_EVENT_TYPE = "COMPLETE"

__all__ = [
    "DEFAULT_EVENT_TIME",
    "DEFAULT_EVENT_TYPE",
    "LineageExport",
    "lineage_event",
    "to_json",
]


@dataclass(frozen=True)
class LineageExport:
    """Спецификация одного экспортируемого ``RunEvent`` (§10.5).

    Поля хранятся плоско; :meth:`as_dict` собирает готовый OpenLineage
    ``RunEvent`` JSON-документ, делегируя нормализацию датасетов и валидацию
    обязательных полей :func:`~kg_common.lineage_openlineage.to_openlineage_event`.
    """

    job: str
    run_id: str
    inputs: tuple[DatasetLike, ...] = field(default_factory=tuple)
    outputs: tuple[DatasetLike, ...] = field(default_factory=tuple)
    event_type: str = DEFAULT_EVENT_TYPE
    event_time: str = DEFAULT_EVENT_TIME
    namespace: str = DEFAULT_NAMESPACE
    producer: str = DEFAULT_PRODUCER

    def as_dict(self) -> dict[str, Any]:
        """OpenLineage ``RunEvent`` JSON-документ (§10.5)."""
        return to_openlineage_event(
            self.run_id,
            self.job,
            self.event_type,
            list(self.inputs),
            list(self.outputs),
            producer=self.producer,
            event_time=self.event_time,
            namespace=self.namespace,
        )


def lineage_event(
    job: str,
    run_id: str,
    inputs: Sequence[DatasetLike] | None,
    outputs: Sequence[DatasetLike] | None,
    *,
    event_type: str = DEFAULT_EVENT_TYPE,
    event_time: str = DEFAULT_EVENT_TIME,
    namespace: str = DEFAULT_NAMESPACE,
    producer: str = DEFAULT_PRODUCER,
) -> dict[str, Any]:
    """Собрать один OpenLineage ``RunEvent`` из ``job``/``run_id`` и io (§10.5).

    ``inputs``/``outputs`` — имена датасетов (``str``) или готовые
    ``{namespace, name}`` mapping'и; каждый рендерится в OpenLineage-датасет
    ``{"namespace": …, "name": …}`` внутри списков ``inputs``/``outputs``.
    ``event_type`` обязан быть валидным OpenLineage RunState (иначе
    ``ValueError``). Пустые io дают пустые списки. По умолчанию ``event_time``
    детерминирован (см. :data:`DEFAULT_EVENT_TIME`).
    """
    export = LineageExport(
        job=job,
        run_id=run_id,
        inputs=tuple(inputs or ()),
        outputs=tuple(outputs or ()),
        event_type=event_type,
        event_time=event_time,
        namespace=namespace,
        producer=producer,
    )
    return export.as_dict()


def to_json(event: Mapping[str, Any], *, indent: int | None = None) -> str:
    """Детерминированно сериализовать ``RunEvent`` в JSON-строку (§10.5).

    Ключи сортируются (``sort_keys=True``) — одинаковые события дают
    побайтово одинаковый JSON; ``json.loads(to_json(ev)) == ev`` (round-trip).
    """
    return json.dumps(event, indent=indent, sort_keys=True, ensure_ascii=False)
