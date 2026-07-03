"""Structured §6.2 graph-query request body for §14.6 graph endpoints.

Пример тела графового запроса из §6.2 (``query_type``, ``material``, вложенный
``processing``, ``property``, ``filters``, ``include_evidence``,
``include_graph``) — центральный контракт §14.6, но до сих пор роутер запросов
принимал только свободный текст. Модуль на чистом stdlib даёт неизменяемые
датаклассы этого тела и валидирующий парсер, отбрасывающий ``None`` при
сериализации и проверяющий ``query_type`` по белому списку и ``min_confidence``
в диапазоне ``[0.0, 1.0]``.

The §6.2 example graph-query body is central to §14.6 yet was unmodeled — the
query router only accepted free text. Pure standard library:

* :class:`Processing`     — frozen ``{operation, temperature_c, time_h}``.
* :class:`QueryFilters`   — frozen ``{min_confidence, verified_only, date_from}``.
* :class:`GraphQueryBody` — frozen top-level body with nested ``as_dict``.
* :func:`parse_graph_query` — validate a wire mapping into a body or raise.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Допустимые типы графовых запросов §6.2/§14.6 / allowed §6.2 query types.
_QUERY_TYPES: frozenset[str] = frozenset(
    {
        "material_regime_property",
        "material_property",
        "property_material",
        "regime_property",
        "path",
        "neighborhood",
    }
)


@dataclass(frozen=True)
class Processing:
    """Неизменяемый блок режима обработки §6.2 / frozen §6.2 processing block.

    Все поля необязательны: частичный вход ``{'operation': 'aging'}`` оставляет
    ``temperature_c`` и ``time_h`` равными ``None``. :meth:`as_dict` опускает
    любые ``None``-поля.

    All fields are optional; a partial input keeps the missing ones ``None``.
    :meth:`as_dict` omits any ``None`` field entirely.
    """

    operation: str | None = None
    temperature_c: float | None = None
    time_h: float | None = None

    def as_dict(self) -> dict[str, object]:
        """Вложенный dict без ``None``-полей / nested dict omitting ``None``."""
        out: dict[str, object] = {}
        if self.operation is not None:
            out["operation"] = self.operation
        if self.temperature_c is not None:
            out["temperature_c"] = self.temperature_c
        if self.time_h is not None:
            out["time_h"] = self.time_h
        return out


@dataclass(frozen=True)
class QueryFilters:
    """Неизменяемый блок фильтров §6.2 / frozen §6.2 filters block.

    ``min_confidence`` — порог доверия в ``[0.0, 1.0]``; ``verified_only`` —
    только подтверждённые связи; ``date_from`` — нижняя граница даты (ISO) или
    ``None``. Значения по умолчанию задают «пустой» фильтр §14.6.

    Defaults model an empty §14.6 filter: no confidence floor, unverified
    included, no date lower bound.
    """

    min_confidence: float = 0.0
    verified_only: bool = False
    date_from: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Вложенный dict фильтров; ``date_from`` опускается при ``None``."""
        out: dict[str, object] = {
            "min_confidence": self.min_confidence,
            "verified_only": self.verified_only,
        }
        if self.date_from is not None:
            out["date_from"] = self.date_from
        return out


@dataclass(frozen=True)
class GraphQueryBody:
    """Неизменяемое тело графового запроса §6.2 / frozen §6.2 graph-query body.

    Верхнеуровневые поля §6.2 с вложенными :class:`Processing` и
    :class:`QueryFilters`. :meth:`as_dict` строит вложенную проводную форму,
    опуская ``None`` ``material``/``processing``/``property`` и пустой
    ``processing`` (без непустых полей).

    Top-level §6.2 fields with nested processing and filters. :meth:`as_dict`
    produces the nested wire form, omitting ``None`` ``material``/``processing``/
    ``property`` and an all-``None`` ``processing``.
    """

    query_type: str
    material: str | None
    processing: Processing | None
    property: str | None
    filters: QueryFilters
    include_evidence: bool
    include_graph: bool

    def as_dict(self) -> dict[str, object]:
        """Вложенная проводная форма §6.2 без ``None`` / nested §6.2 wire dict."""
        out: dict[str, object] = {"query_type": self.query_type}
        if self.material is not None:
            out["material"] = self.material
        if self.processing is not None:
            processing = self.processing.as_dict()
            if processing:
                out["processing"] = processing
        if self.property is not None:
            out["property"] = self.property
        out["filters"] = self.filters.as_dict()
        out["include_evidence"] = self.include_evidence
        out["include_graph"] = self.include_graph
        return out


def _parse_processing(raw: object) -> Processing | None:
    """Разобрать вложенный ``processing`` §6.2 / parse the §6.2 processing block.

    ``None`` вход даёт ``None``; частичный dict оставляет отсутствующие поля
    ``None``. Не-mapping вход считается ошибкой контракта.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("processing must be a mapping or omitted")
    return Processing(
        operation=raw.get("operation"),
        temperature_c=raw.get("temperature_c"),
        time_h=raw.get("time_h"),
    )


def _parse_filters(raw: object) -> QueryFilters:
    """Разобрать вложенный ``filters`` §6.2 / parse the §6.2 filters block.

    Отсутствующий блок даёт значения по умолчанию
    ``QueryFilters(0.0, False, None)``. ``min_confidence`` проверяется на
    диапазон ``[0.0, 1.0]``, иначе :class:`ValueError`.
    """
    if raw is None:
        return QueryFilters()
    if not isinstance(raw, Mapping):
        raise ValueError("filters must be a mapping or omitted")
    min_confidence = float(raw.get("min_confidence", 0.0))
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError(f"min_confidence must be within [0.0, 1.0], got {min_confidence!r}")
    return QueryFilters(
        min_confidence=min_confidence,
        verified_only=bool(raw.get("verified_only", False)),
        date_from=raw.get("date_from"),
    )


def parse_graph_query(body: Mapping[str, object]) -> GraphQueryBody:
    """Разобрать и валидировать §6.2 тело графового запроса / parse §6.2 body.

    ``query_type`` обязателен и проверяется по белому списку (в т.ч.
    ``'material_regime_property'``); неизвестное значение — :class:`ValueError`.
    ``filters.min_confidence`` должен быть в ``[0.0, 1.0]``. ``include_evidence``
    и ``include_graph`` по умолчанию ``True`` при отсутствии.

    ``query_type`` is required and checked against the whitelist; an unknown
    value raises :class:`ValueError`. ``min_confidence`` must lie in
    ``[0.0, 1.0]``. Both ``include_*`` flags default to ``True`` when absent.
    """
    query_type = body.get("query_type")
    if not isinstance(query_type, str) or query_type not in _QUERY_TYPES:
        raise ValueError(f"unknown query_type: {query_type!r}")
    return GraphQueryBody(
        query_type=query_type,
        material=body.get("material"),
        processing=_parse_processing(body.get("processing")),
        property=body.get("property"),
        filters=_parse_filters(body.get("filters")),
        include_evidence=bool(body.get("include_evidence", True)),
        include_graph=bool(body.get("include_graph", True)),
    )
