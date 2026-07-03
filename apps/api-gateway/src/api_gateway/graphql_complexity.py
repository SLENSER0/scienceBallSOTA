"""GraphQL query depth/complexity guard for the optional proxy (§14.13).

Лёгкий оценщик сложности GraphQL-запроса на чистом stdlib: без внешней
graphql-библиотеки он считает максимальную вложенность фигурных скобок
(``depth``) и число идентификаторов-полей внутри selection set-ов
(``field_count``), чтобы отклонять слишком глубокие или дорогие запросы на
необязательном ``POST /graphql``. :func:`estimate_complexity` возвращает
замороженный :class:`ComplexityResult`, а :func:`is_within_limits` даёт
булев вердикт по настраиваемым лимитам.

A lightweight GraphQL complexity estimator on the standard library only: with no
external graphql dependency it measures the maximum nesting of ``{``/``}``
(``depth``) and the number of field identifiers inside selection sets
(``field_count``) to reject overly deep or expensive queries on the optional
``POST /graphql`` proxy. :func:`estimate_complexity` returns a frozen
:class:`ComplexityResult`; :func:`is_within_limits` gives a boolean verdict
against configurable limits.

* :class:`ComplexityResult` — frozen ``{depth, field_count, over_limit}`` w/ :meth:`as_dict`.
* :func:`estimate_complexity` — query text → measured depth and field count.
* :func:`is_within_limits`   — query text vs ``max_depth`` / ``max_fields`` → bool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Дефолтные лимиты guard-а / default guard limits (§14.13).
DEFAULT_MAX_DEPTH = 10
DEFAULT_MAX_FIELDS = 200


@dataclass(frozen=True)
class ComplexityResult:
    """Итог оценки сложности запроса / measured query-complexity outcome (§14.13).

    ``depth`` — максимальная вложенность фигурных скобок, ``field_count`` — число
    идентификаторов-полей внутри selection set-ов, ``over_limit`` — превышен ли
    любой из дефолтных лимитов (:data:`DEFAULT_MAX_DEPTH` / :data:`DEFAULT_MAX_FIELDS`).
    """

    depth: int
    field_count: int
    over_limit: bool

    def as_dict(self) -> dict[str, Any]:
        """Плоское представление для логов/JSON / flat mapping for logs/JSON."""
        return {
            "depth": self.depth,
            "field_count": self.field_count,
            "over_limit": self.over_limit,
        }


def _scan(query: str) -> tuple[int, int]:
    """Один проход: вернуть ``(max_depth, field_count)`` / single pass over the query.

    Сканируем посимвольно: ``{`` увеличивает текущую вложенность (обновляя
    максимум), ``}`` уменьшает её (не ниже нуля), а любой идентификатор
    ``[A-Za-z_][A-Za-z0-9_]*``, встреченный при вложенности ≥ 1, считается полем.
    """
    depth = 0
    max_depth = 0
    field_count = 0
    i = 0
    n = len(query)
    while i < n:
        c = query[i]
        if c == "{":
            depth += 1
            if depth > max_depth:
                max_depth = depth
            i += 1
        elif c == "}":
            if depth > 0:
                depth -= 1
            i += 1
        elif c.isalpha() or c == "_":
            j = i + 1
            while j < n and (query[j].isalnum() or query[j] == "_"):
                j += 1
            if depth > 0:
                field_count += 1
            i = j
        else:
            i += 1
    return max_depth, field_count


def estimate_complexity(query: str) -> ComplexityResult:
    """Оценить глубину и число полей запроса / measure query depth and field count (§14.13).

    ``depth`` — максимальная вложенность ``{``/``}``, ``field_count`` — количество
    идентификаторов внутри selection set-ов. ``over_limit`` вычисляется по
    дефолтным лимитам (:data:`DEFAULT_MAX_DEPTH` / :data:`DEFAULT_MAX_FIELDS`).
    """
    depth, field_count = _scan(query)
    over_limit = depth > DEFAULT_MAX_DEPTH or field_count > DEFAULT_MAX_FIELDS
    return ComplexityResult(depth=depth, field_count=field_count, over_limit=over_limit)


def is_within_limits(
    query: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_fields: int = DEFAULT_MAX_FIELDS,
) -> bool:
    """Уложился ли запрос в лимиты / does the query stay within the limits (§14.13).

    Возвращает ``True``, только если и глубина ≤ ``max_depth``, и число полей
    ≤ ``max_fields``; иначе ``False`` (запрос надо отклонить как слишком дорогой).
    """
    depth, field_count = _scan(query)
    return depth <= max_depth and field_count <= max_fields
