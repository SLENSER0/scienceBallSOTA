"""Shared pagination / validation schemas (§14.2).

Общие схемы постраничного вывода и валидации, переиспользуемые роутерами
(experiments, search, gaps, …). Один и тот же конверт списка —
``{total, count, limit, offset, items}`` — уже отдаёт ``routers/experiments.py``;
:func:`build_paginated` централизует его, а :class:`PageParams` и
:func:`parse_sort` дают единые правила валидации ``limit/offset/sort``.

Namespacing: this is a flat module (``schemas_common``), NOT a ``schemas``
subpackage — routers import ``from api_gateway.schemas_common import ...``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PageParams(BaseModel):
    """Параметры постраничного вывода / pagination query params (§14.2).

    ``limit`` зажат в ``[1, 200]`` (значение по умолчанию 50), ``offset`` — от 0,
    ``sort`` опционален и парсится через :func:`parse_sort` с белым списком полей.
    """

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort: str | None = None


def build_paginated(items: list[Any], total: int, params: PageParams) -> dict[str, Any]:
    """Собрать конверт списка ``{total, count, limit, offset, items}`` (§14.2).

    ``count`` всегда равен ``len(items)`` (размер текущей страницы), тогда как
    ``total`` — независимое число всех совпавших записей до пагинации.
    """
    return {
        "total": total,
        "count": len(items),
        "limit": params.limit,
        "offset": params.offset,
        "items": items,
    }


def parse_sort(sort: str | None, allowed: set[str]) -> tuple[str, str]:
    """Разобрать строку сортировки ``"field:direction"`` (§14.2).

    Принимает ``"name"`` (направление по умолчанию ``asc``) или ``"name:desc"``.
    Поле обязано входить в белый список ``allowed``; направление — ``asc``/``desc``.
    Любое отклонение — :class:`ValueError` (неизвестное поле / направление / пустое).
    """
    if sort is None or not sort.strip():
        raise ValueError("sort is empty")
    field, _, direction = sort.partition(":")
    field = field.strip()
    direction = direction.strip().lower() or "asc"
    if field not in allowed:
        raise ValueError(f"unknown sort field: {field!r}")
    if direction not in ("asc", "desc"):
        raise ValueError(f"unknown sort direction: {direction!r}")
    return field, direction
