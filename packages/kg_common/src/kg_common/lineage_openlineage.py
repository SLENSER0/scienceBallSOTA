"""OpenLineage-format lineage events (§10.9 Marquez/OpenLineage alternative).

Pure-python emitter of `OpenLineage <https://openlineage.io>`_ ``RunEvent``
JSON documents — событие происхождения прогона конвейера в открытом формате,
пригодном для Marquez/любого OpenLineage-совместимого бэкенда — БЕЗ marquez
клиента и сетевых зависимостей (§10.9 «альтернатива: экспорт lineage в формате
OpenLineage»). Дополняет встроенный каталог
:mod:`kg_common.storage.metadata_catalog`: те же рёбра ``upstream → asset``
(§10.5) переводятся в ``inputs``/``outputs`` датасеты события.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# -- constants (§10.9 OpenLineage RunEvent envelope) ----------------------
#: Допустимые типы события жизненного цикла прогона (OpenLineage RunState).
EVENT_TYPES: frozenset[str] = frozenset({"START", "RUNNING", "COMPLETE", "ABORT", "FAIL"})
#: Терминальные состояния — которыми может завершиться :func:`emit_run`.
TERMINAL_EVENT_TYPES: frozenset[str] = frozenset({"COMPLETE", "ABORT", "FAIL"})

#: Пространство имён по умолчанию для job/датасетов (namespace конвейера).
DEFAULT_NAMESPACE = "scienceball"
#: ``producer`` — URI кода, породившего событие (§10.9).
DEFAULT_PRODUCER = "https://github.com/scienceball/kg_common#lineage_openlineage"
#: ``schemaURL`` — версия спецификации OpenLineage для ``RunEvent``.
SCHEMA_URL = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"

#: Тип элемента inputs/outputs: имя-строка или готовый датасет-mapping.
DatasetLike = str | Mapping[str, str]

__all__ = [
    "DEFAULT_NAMESPACE",
    "DEFAULT_PRODUCER",
    "EVENT_TYPES",
    "SCHEMA_URL",
    "TERMINAL_EVENT_TYPES",
    "OpenLineageEvent",
    "emit_run",
    "from_lineage_edges",
    "to_openlineage_event",
]


def _require(value: object, field: str) -> str:
    """Проверить обязательное строковое поле (§10.9 required fields)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"OpenLineage RunEvent requires non-empty {field!r}")
    return str(value)


def _to_dataset(item: DatasetLike, *, namespace: str = DEFAULT_NAMESPACE) -> dict[str, str]:
    """Нормализовать вход/выход к OpenLineage-датасету ``{namespace, name}``."""
    if isinstance(item, Mapping):
        name = item.get("name")
        if not name:
            raise ValueError(f"dataset mapping requires a 'name': {item!r}")
        return {"namespace": str(item.get("namespace", namespace)), "name": str(name)}
    name = str(item)
    if not name:
        raise ValueError("dataset name must be non-empty")
    return {"namespace": namespace, "name": name}


def _edge_field(edge: Mapping[str, Any] | Any, field: str) -> str:
    """Достать поле ребра lineage из dict или dataclass (LineageEdge §10.5)."""
    if isinstance(edge, Mapping):
        return str(edge.get(field, "") or "")
    return str(getattr(edge, field, "") or "")


@dataclass(frozen=True)
class OpenLineageEvent:
    """Одно OpenLineage ``RunEvent`` (§10.9), сериализуемое в JSON-форму.

    Поля хранятся плоско (Python snake_case), а :meth:`as_dict` собирает
    вложенную структуру со «схемными» ключами OpenLineage (``eventType``,
    ``run.runId``, ``job.namespace/name`` …).
    """

    event_type: str
    event_time: str
    run_id: str
    job_namespace: str
    job_name: str
    inputs: tuple[Mapping[str, str], ...]
    outputs: tuple[Mapping[str, str], ...]
    producer: str
    schema_url: str = SCHEMA_URL

    def as_dict(self) -> dict[str, Any]:
        """OpenLineage ``RunEvent`` JSON-документ (§10.9)."""
        return {
            "eventType": self.event_type,
            "eventTime": self.event_time,
            "run": {"runId": self.run_id},
            "job": {"namespace": self.job_namespace, "name": self.job_name},
            "inputs": [dict(d) for d in self.inputs],
            "outputs": [dict(d) for d in self.outputs],
            "producer": self.producer,
            "schemaURL": self.schema_url,
        }


def to_openlineage_event(
    run_id: str,
    job_name: str,
    event_type: str,
    inputs: Sequence[DatasetLike] | None,
    outputs: Sequence[DatasetLike] | None,
    *,
    producer: str = DEFAULT_PRODUCER,
    event_time: str,
    namespace: str = DEFAULT_NAMESPACE,
) -> dict[str, Any]:
    """Собрать один OpenLineage ``RunEvent`` (§10.9).

    ``event_type`` обязан быть из :data:`EVENT_TYPES`; ``run_id``/``job_name``/
    ``event_time`` обязательны (иначе ``ValueError``). ``inputs``/``outputs`` —
    имена датасетов или готовые ``{namespace, name}`` mapping'и.
    """
    run_id = _require(run_id, "run_id")
    job_name = _require(job_name, "job_name")
    event_time = _require(event_time, "event_time")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"invalid eventType {event_type!r}; expected one of {sorted(EVENT_TYPES)}")
    event = OpenLineageEvent(
        event_type=event_type,
        event_time=event_time,
        run_id=run_id,
        job_namespace=namespace,
        job_name=job_name,
        inputs=tuple(_to_dataset(x, namespace=namespace) for x in (inputs or [])),
        outputs=tuple(_to_dataset(x, namespace=namespace) for x in (outputs or [])),
        producer=producer,
    )
    return event.as_dict()


def emit_run(
    job_name: str,
    inputs: Sequence[DatasetLike] | None,
    outputs: Sequence[DatasetLike] | None,
    run_id: str,
    event_time: str,
    status: str = "COMPLETE",
) -> list[dict[str, Any]]:
    """Пара событий одного прогона: ``START`` + терминальное (§10.9).

    ``status`` (``COMPLETE``/``FAIL``/``ABORT``) задаёт тип второго события;
    оба события несут один и тот же ``run.runId`` и одинаковые inputs/outputs.
    """
    if status not in TERMINAL_EVENT_TYPES:
        raise ValueError(
            f"terminal status must be one of {sorted(TERMINAL_EVENT_TYPES)}, got {status!r}"
        )
    start = to_openlineage_event(run_id, job_name, "START", inputs, outputs, event_time=event_time)
    finish = to_openlineage_event(run_id, job_name, status, inputs, outputs, event_time=event_time)
    return [start, finish]


def from_lineage_edges(
    edges: Iterable[Mapping[str, Any] | Any],
    *,
    run_id: str,
    job_name: str,
    event_time: str,
    event_type: str = "COMPLETE",
) -> dict[str, Any]:
    """Перевести рёбра каталога lineage в OpenLineage ``RunEvent`` (§10.9).

    Принимает записи вида ``{asset, upstream}`` (или
    :class:`~kg_common.storage.metadata_catalog.LineageEdge`): ``upstream`` →
    ``inputs``, ``asset`` → ``outputs`` (пустые upstream = корневой asset,
    пропускаются; порядок сохранён, дубликаты убраны).
    """
    inputs: list[str] = []
    outputs: list[str] = []
    seen_in: set[str] = set()
    seen_out: set[str] = set()
    for edge in edges:
        asset = _edge_field(edge, "asset")
        upstream = _edge_field(edge, "upstream")
        if asset and asset not in seen_out:
            seen_out.add(asset)
            outputs.append(asset)
        if upstream and upstream not in seen_in:
            seen_in.add(upstream)
            inputs.append(upstream)
    return to_openlineage_event(
        run_id, job_name, event_type, inputs, outputs, event_time=event_time
    )
