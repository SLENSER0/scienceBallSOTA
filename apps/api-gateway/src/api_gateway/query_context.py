"""Graph ``queryContext`` transparency carrier for graph responses (§14.6/§5.3).

Каждый графовый ответ по §14.6 обязан нести ``queryContext`` с исходным
запросом пользователя, применёнными фильтрами и сгенерированным Cypher, чтобы
клиент видел, как именно получен результат. Этот модуль на чистом stdlib даёт
неизменяемый носитель и билдер, который отбрасывает пустые фильтры, нормализует
пробелы в Cypher и приводит форму к camelCase проводному виду §5.3.

Every graph response in §14.6 must carry a ``queryContext`` exposing the
original user query, the applied filters and the generated Cypher so the client
can see how the result was produced. Pure standard library:

* :class:`QueryContext`        — frozen ``{user_query, filters, generated_cypher}``.
* :meth:`QueryContext.as_dict` — §5.3 camelCase wire form.
* :func:`build_query_context`  — drop empty filters, normalise Cypher whitespace.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

# Прогоны пробелов/переводов строк → один пробел / whitespace runs → one space.
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class QueryContext:
    """Неизменяемый носитель прозрачности графового запроса (§14.6/§5.3).

    Frozen carrier for one graph response's transparency block: the verbatim
    ``user_query``, the applied ``filters`` and the ``generated_cypher``.
    :meth:`as_dict` renders the §5.3 camelCase wire form
    ``{userQuery, filters, generatedCypher}``.
    """

    user_query: str
    filters: Mapping[str, object]
    generated_cypher: str

    def as_dict(self) -> dict[str, object]:
        """§5.3 camelCase проводная форма / camelCase wire dict (§5.3).

        Keys are exactly ``userQuery``, ``filters`` and ``generatedCypher``;
        ``filters`` is copied into a plain ``dict`` so the wire form never leaks
        the internal (possibly read-only) mapping.
        """
        return {
            "userQuery": self.user_query,
            "filters": dict(self.filters),
            "generatedCypher": self.generated_cypher,
        }


def build_query_context(
    user_query: str,
    filters: Mapping[str, object] | None,
    cypher: str | None,
) -> QueryContext:
    """Собрать :class:`QueryContext` с очисткой фильтров и Cypher (§14.6/§5.3).

    Отбрасывает фильтры со значением ``None`` или пустым, схлопывает прогоны
    пробелов/переводов строк в Cypher до одного пробела и обрезает края,
    приводит ``None``-Cypher к пустой строке. ``user_query`` сохраняется дословно.

    Drops filter entries whose value is ``None`` or empty, collapses runs of
    whitespace/newlines in ``cypher`` to a single space then strips it, and
    coerces a ``None`` cypher to ``''``. The ``user_query`` is kept verbatim.
    """
    cleaned = {key: value for key, value in (filters or {}).items() if not _is_empty(value)}
    normalised = _WHITESPACE.sub(" ", cypher).strip() if cypher is not None else ""
    return QueryContext(
        user_query=user_query,
        filters=MappingProxyType(cleaned),
        generated_cypher=normalised,
    )


def _is_empty(value: object) -> bool:
    """Пустой фильтр: ``None`` или пустой контейнер/строка / empty filter value.

    Treats ``None`` and any empty string/collection as droppable, while keeping
    falsy-but-meaningful values such as ``False`` and ``0``.
    """
    if value is None:
        return True
    if isinstance(value, (str, bytes, list, tuple, set, frozenset, dict)):
        return len(value) == 0
    return False
