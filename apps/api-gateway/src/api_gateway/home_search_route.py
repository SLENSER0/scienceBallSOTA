"""Резолвер режима поиска домашней страницы → маршрут (§17.6).

Чистый резолвер сегментированного контрола §17.6 на домашней странице.
Пять режимов (Question|Entity|Experiment|Document|Gap) преобразуются в целевой
маршрут SPA и словарь параметров. Модуль без побочных эффектов, только stdlib:
константа :data:`MODE_ROUTES`, неизменяемый :class:`SearchRoute` и функция
:func:`resolve_search_route`. Сопоставление режима регистронезависимо; текст
запроса кладётся в ``params['q']``; переданные фильтры сливаются в параметры;
неизвестный режим → :class:`ValueError`.

Pure resolver for the §17.6 Home segmented control. The five modes
(Question|Entity|Experiment|Document|Gap) map to a target SPA route plus a
params dict. Side-effect-free, stdlib only: the :data:`MODE_ROUTES` constant,
the immutable :class:`SearchRoute`, and :func:`resolve_search_route`. Mode
matching is case-insensitive; the query goes under ``params['q']``; provided
filters merge into params; an unknown mode raises :class:`ValueError`.

* :data:`MODE_ROUTES` — пять режимов (строчными) → путь / five modes → path.
* :class:`SearchRoute` — неизменяемый результат с :meth:`as_dict`.
* :func:`resolve_search_route` — режим + запрос → :class:`SearchRoute`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Пять режимов §17.6 (строчными) → маршрут SPA / five §17.6 modes → SPA route.
MODE_ROUTES: dict[str, str] = {
    "question": "/chat",
    "entity": "/graph",
    "experiment": "/experiments",
    "document": "/document",
    "gap": "/gaps",
}


@dataclass(frozen=True, slots=True)
class SearchRoute:
    """Неизменяемый результат резолвинга режима поиска (§17.6).

    Immutable result of resolving a §17.6 Home search mode. ``mode`` is the
    normalised (lowercased) mode; ``path`` is the target SPA route; ``params``
    carries the query under ``'q'`` plus any merged filters. :meth:`as_dict`
    yields the wire form with keys ``mode``/``path``/``params``.
    """

    mode: str
    path: str
    params: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление маршрута / wire form (§17.6).

        Возвращает словарь с ключами ``mode``/``path``/``params``; ``params``
        копируется, чтобы результат оставался неизменяемым.
        """
        return {"mode": self.mode, "path": self.path, "params": dict(self.params)}


def resolve_search_route(
    mode: str, query: str, *, filters: dict[str, Any] | None = None
) -> SearchRoute:
    """Разрешить режим поиска §17.6 в целевой маршрут SPA.

    Сопоставление режима регистронезависимо (нормализуется в нижний регистр).
    Текст запроса помещается в ``params['q']``; любые ``filters`` сливаются в
    параметры (побеждают значения фильтров, кроме зарезервированного ``'q'``).

    Resolve a §17.6 Home search mode to its target SPA route. Mode matching is
    case-insensitive (normalised to lowercase). The query goes under
    ``params['q']``; any ``filters`` merge into params.

    :raises ValueError: если режим не входит в :data:`MODE_ROUTES` / when the
        mode is not one of the five known §17.6 modes.
    """
    normalised = mode.lower()
    path = MODE_ROUTES.get(normalised)
    if path is None:
        raise ValueError(f"unknown search mode: {mode!r}")

    params: dict[str, Any] = {"q": query}
    if filters:
        params.update(filters)
        params["q"] = query
    return SearchRoute(mode=normalised, path=path, params=params)
