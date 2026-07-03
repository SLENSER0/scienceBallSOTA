"""Фильтры списка документов для ``GET /documents`` (§14.9).

Полный набор фильтров эндпоинта ``GET /documents`` из §14.9, по образцу
``experiment_filters.py``/``gap_filter.py``, но для документов (своего не было).
Модуль на чистом stdlib: разбор query-параметров в неизменяемый
:class:`DocumentFilters`, сериализация через :meth:`DocumentFilters.as_dict`
(пропускает ``None``) и предикат :func:`matches` для отбора строк-документов.

Full filter set for the ``GET /documents`` endpoint (§14.9), mirroring the
``experiment_filters.py``/``gap_filter.py`` pattern but for documents (none
existed). Pure stdlib: parse query params into an immutable
:class:`DocumentFilters`, serialise via :meth:`DocumentFilters.as_dict`
(omitting ``None`` fields), and test rows with :func:`matches`.

* :data:`DOC_STATUSES` — допустимые статусы ингеста / allowed ingest statuses.
* :class:`DocumentFilters` — неизменяемый фильтр с :meth:`as_dict`.
* :func:`parse_document_filters` — query mapping → ``DocumentFilters``.
* :func:`matches` — document dict + filters → ``bool``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

#: Допустимые статусы ингеста документа §14.9 / allowed ingest statuses (§14.9).
DOC_STATUSES: frozenset[str] = frozenset({"queued", "running", "succeeded", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class DocumentFilters:
    """Неизменяемый набор фильтров ``GET /documents`` (§14.9).

    Immutable filter set encoding the §14.9 ``GET /documents`` query. Every
    field is optional. :meth:`as_dict` yields the wire form with ``None`` fields
    omitted so the set of *active* filters is explicit.
    """

    source_type: str | None = None
    owner: str | None = None
    lab: str | None = None
    status: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление только активных фильтров (§14.9).

        Пропускает ``None``-поля, поэтому словарь содержит ровно набор
        *заданных* фильтров.

        Emits only active filters: ``None`` fields are omitted, so the dict is
        exactly the set of *set* filters.
        """
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            out[f.name] = value
        return out


def parse_document_filters(params: Mapping[str, Any]) -> DocumentFilters:
    """Разобрать query-параметры в :class:`DocumentFilters` (§14.9).

    ``status`` (если задан) обязан лежать в :data:`DOC_STATUSES`. Остальные поля
    берутся как строки без преобразования.

    ``status`` (when set) must be in :data:`DOC_STATUSES`. Other fields are read
    as strings without coercion.

    :raises ValueError: если ``status`` не входит в :data:`DOC_STATUSES` /
        when ``status`` is not an allowed ingest status.
    """
    status = params.get("status")
    if status is not None and status not in DOC_STATUSES:
        raise ValueError(f"unknown document status: {status!r}")

    return DocumentFilters(
        source_type=params.get("source_type"),
        owner=params.get("owner"),
        lab=params.get("lab"),
        status=status,
        date_from=params.get("date_from"),
        date_to=params.get("date_to"),
    )


def matches(doc: dict[str, Any], f: DocumentFilters) -> bool:
    """Проверить документ против фильтров (§14.9).

    Test one document dict against the active filters. ``source_type``,
    ``owner``, ``lab`` и ``status`` сравниваются на равенство; границы дат
    сравниваются как ISO-строки: ``date_from`` требует ``doc['created_at'] >=
    date_from``, ``date_to`` требует ``doc['created_at'] <= date_to``.
    Absent fields on ``doc`` fail the corresponding active filter.
    """
    if f.source_type is not None and doc.get("source_type") != f.source_type:
        return False
    if f.owner is not None and doc.get("owner") != f.owner:
        return False
    if f.lab is not None and doc.get("lab") != f.lab:
        return False
    if f.status is not None and doc.get("status") != f.status:
        return False
    if f.date_from is not None:
        created = doc.get("created_at")
        if not isinstance(created, str) or created < f.date_from:
            return False
    if f.date_to is not None:
        created = doc.get("created_at")
        if not isinstance(created, str) or created > f.date_to:
            return False
    return True
