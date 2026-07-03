"""Тесты резолвера режима поиска домашней страницы (§17.6).

Ручные проверки чистого резолвера §17.6: сопоставление пяти режимов с
маршрутами, регистронезависимость, размещение запроса в ``params['q']``,
слияние фильтров, ошибка на неизвестном режиме и форма :meth:`as_dict`.

Hand-checkable tests for the §17.6 resolver: mode→route mapping, case
insensitivity, query under ``params['q']``, filter merge, ValueError on an
unknown mode, and the :meth:`as_dict` shape.
"""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.home_search_route import (
    MODE_ROUTES,
    SearchRoute,
    resolve_search_route,
)


def test_question_routes_to_chat() -> None:
    """Режим 'Question' → '/chat' / mode 'Question' maps to '/chat'."""
    assert resolve_search_route("Question", "al-cu").path == "/chat"


def test_experiment_routes_to_experiments() -> None:
    """Режим 'Experiment' → '/experiments'."""
    assert resolve_search_route("Experiment", "x").path == "/experiments"


def test_gap_routes_to_gaps() -> None:
    """Режим 'Gap' → '/gaps'."""
    assert resolve_search_route("Gap", "x").path == "/gaps"


def test_document_routes_to_document() -> None:
    """Режим 'Document' → '/document'."""
    assert resolve_search_route("Document", "x").path == "/document"


def test_entity_routes_to_graph() -> None:
    """Режим 'Entity' → '/graph' (пятый режим §17.6)."""
    assert resolve_search_route("Entity", "x").path == "/graph"


def test_mode_matching_is_case_insensitive() -> None:
    """'QUESTION' любого регистра эквивалентен 'question'."""
    upper = resolve_search_route("QUESTION", "al-cu")
    lower = resolve_search_route("question", "al-cu")
    assert upper.path == lower.path == "/chat"
    assert upper.mode == lower.mode == "question"


def test_query_placed_under_q() -> None:
    """Текст запроса кладётся в ``params['q']`` / query under params['q']."""
    route = resolve_search_route("Question", "grain boundary")
    assert route.params["q"] == "grain boundary"


def test_filters_merged_into_params() -> None:
    """Фильтры сливаются в параметры / filters merge into params."""
    route = resolve_search_route("Entity", "al", filters={"material": "Al"})
    assert route.params["material"] == "Al"
    assert route.params["q"] == "al"


def test_filters_do_not_clobber_query() -> None:
    """Фильтр ``q`` не затирает переданный запрос / filters keep the query."""
    route = resolve_search_route("Question", "real-q", filters={"q": "spoof"})
    assert route.params["q"] == "real-q"


def test_unknown_mode_raises() -> None:
    """Неизвестный режим → ValueError / unknown mode raises ValueError."""
    with pytest.raises(ValueError):
        resolve_search_route("bogus", "x")


def test_as_dict_shape() -> None:
    """``as_dict`` содержит ключи mode/path/params / expected keys present."""
    route = resolve_search_route("Gap", "x", filters={"status": "open"})
    d = route.as_dict()
    assert set(d) == {"mode", "path", "params"}
    assert d["mode"] == "gap"
    assert d["path"] == "/gaps"
    assert d["params"] == {"q": "x", "status": "open"}


def test_as_dict_params_is_copy() -> None:
    """``as_dict`` копирует params, не давая мутировать результат."""
    route = resolve_search_route("Question", "x")
    route.as_dict()["params"]["injected"] = True
    assert "injected" not in route.params


def test_mode_routes_constant_covers_five_modes() -> None:
    """:data:`MODE_ROUTES` покрывает ровно пять режимов §17.6."""
    assert MODE_ROUTES == {
        "question": "/chat",
        "entity": "/graph",
        "experiment": "/experiments",
        "document": "/document",
        "gap": "/gaps",
    }


def test_search_route_is_frozen() -> None:
    """:class:`SearchRoute` неизменяем / instances are frozen."""
    route = resolve_search_route("Question", "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        route.mode = "entity"  # type: ignore[misc]
    assert isinstance(route, SearchRoute)
