"""Sort-parameter parsing and stable multi-key ordering (§14.16).

Разбор строки сортировки вида ``"name:desc,created:asc"`` в список ключей
``(field, direction)`` с проверкой по белому списку полей и допустимых
направлений, плюс устойчивая (stable) многоключевая сортировка строк. Модуль —
на чистом stdlib, без зависимостей, поэтому его легко тестировать и переиспользовать.

Parse a sort string such as ``"name:desc,created:asc"`` into a list of
``(field, direction)`` keys, validated against an allow-list of fields and the
permitted directions, then apply a *stable* multi-key sort to rows. Pure stdlib,
dependency-free.

* :class:`SortKey`   — frozen ``(field, direction)`` pair with :meth:`as_dict`.
* :func:`parse_sort` — sort string → ``list[SortKey]`` (raises on bad input).
* :func:`apply_sort` — rows + keys → new stably-sorted ``list``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from typing import Any

ASC = "asc"
DESC = "desc"

#: Допустимые направления сортировки / permitted sort directions.
DIRECTIONS: frozenset[str] = frozenset({ASC, DESC})


@dataclass(frozen=True, slots=True)
class SortKey:
    """Неизменяемый ключ сортировки: поле + направление (§14.16).

    Immutable single sort key. ``field`` is a validated column name and
    ``direction`` is exactly ``"asc"`` or ``"desc"`` (already normalised to
    lower case by :func:`parse_sort`).
    """

    field: str
    direction: str

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление ключа / wire form (§14.16)."""
        return {"field": self.field, "direction": self.direction}


def parse_sort(sort_str: str, allowed: Set[str]) -> list[SortKey]:
    """Разобрать строку сортировки в список ключей ``SortKey`` (§14.16).

    Формат — ``"field[:dir],field[:dir],..."``; направление необязательно и по
    умолчанию ``"asc"``. Направление регистронезависимо и нормализуется в нижний
    регистр. Пустая (или пробельная) строка даёт пустой список ``[]``.

    Format is ``"field[:dir],field[:dir],..."``; the direction is optional and
    defaults to ``"asc"``. Direction matching is case-insensitive and normalised
    to lower case. An empty (or whitespace-only) string yields ``[]``.

    :raises ValueError: пустой токен, отсутствующее имя поля, лишние ``":"``,
        неизвестное поле (нет в ``allowed``) или недопустимое направление.
    """
    if sort_str is None or not sort_str.strip():
        return []
    keys: list[SortKey] = []
    for token in sort_str.split(","):
        raw = token.strip()
        if not raw:
            raise ValueError("empty sort field in sort string")
        parts = raw.split(":")
        if len(parts) > 2:
            raise ValueError(f"malformed sort token: {token!r}")
        field = parts[0].strip()
        if not field:
            raise ValueError(f"missing sort field in token: {token!r}")
        direction = parts[1].strip().lower() if len(parts) == 2 else ASC
        if field not in allowed:
            raise ValueError(f"unknown sort field: {field!r}")
        if direction not in DIRECTIONS:
            raise ValueError(f"invalid sort direction: {direction!r}")
        keys.append(SortKey(field=field, direction=direction))
    return keys


def apply_sort(
    rows: Sequence[Mapping[str, Any]],
    sort: Sequence[SortKey],
) -> list[Mapping[str, Any]]:
    """Устойчиво отсортировать ``rows`` по списку ключей ``sort`` (§14.16).

    Многоключевая сортировка выполняется как последовательность устойчивых
    сортировок от последнего ключа к первому — так самый левый ключ становится
    старшим (primary). Устойчивость Python-сортировки (в т. ч. при
    ``reverse=True``) гарантирует, что строки, равные по всем ключам, сохраняют
    исходный относительный порядок. Пустой ``sort`` возвращает копию входа.

    Multi-key ordering is done as successive stable sorts from the last key to
    the first, so the left-most key becomes primary. Python's sort is stable
    (also under ``reverse=True``), so rows equal on every key keep their input
    order. An empty ``sort`` returns a shallow copy of the input.
    """
    result: list[Mapping[str, Any]] = list(rows)
    for key in reversed(sort):
        result.sort(
            key=lambda row, field=key.field: row[field],
            reverse=key.direction == DESC,
        )
    return result
