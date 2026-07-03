"""Range validation for §14.7 search-endpoint request bodies.

§14.7 поисковые эндпоинты принимают тело с ``query``, ``top_k``, гибридными
``weights`` и опциональным порогом ``min_confidence``, но диапазоны этих полей
до сих пор не проверялись — отрицательный ``top_k`` или ``min_confidence`` вне
``[0, 1]`` доходили до слоя поиска. Модуль на чистом stdlib даёт неизменяемый
:class:`ValidatedSearchRequest` с :meth:`as_dict` и валидатор
:func:`validate_search_request`, отбрасывающий некорректные тела единым
исключением :class:`SearchValidationError`.

The §14.7 search endpoints accept ``query``, ``top_k``, hybrid ``weights`` and
an optional ``min_confidence`` floor, yet their ranges went unchecked. Pure
standard library:

* :class:`SearchValidationError`   — raised for any out-of-range/malformed body.
* :class:`ValidatedSearchRequest`  — frozen validated request with ``as_dict``.
* :func:`validate_search_request`  — validate a wire mapping or raise.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Верхняя граница ``top_k`` §14.7 / the §14.7 upper bound on ``top_k``.
MAX_TOP_K: int = 200

# Значение ``top_k`` по умолчанию §14.7 / the §14.7 default ``top_k``.
_DEFAULT_TOP_K: int = 10


class SearchValidationError(ValueError):
    """Некорректное тело §14.7 поиска / a malformed §14.7 search body.

    Единое исключение для всех нарушений диапазона (пустой ``query``,
    ``top_k`` вне ``1..MAX_TOP_K``, отрицательный вес, нулевая сумма весов,
    ``min_confidence`` вне ``[0, 1]``).

    A single exception for every range violation so callers can map it to one
    HTTP 400 response.
    """


@dataclass(frozen=True)
class ValidatedSearchRequest:
    """Неизменяемый валидированный запрос §14.7 / frozen validated §14.7 request.

    Поля уже проверены :func:`validate_search_request`: ``query`` — непустая
    строка, ``top_k`` в ``1..MAX_TOP_K``, ``weights`` — неотрицательные веса с
    положительной суммой, ``min_confidence`` — ``None`` или ``[0, 1]``.
    :meth:`as_dict` опускает ``min_confidence`` при ``None``.

    Fields are already validated; :meth:`as_dict` renders the wire form and
    omits ``min_confidence`` when ``None``.
    """

    query: str
    top_k: int
    weights: dict[str, float]
    min_confidence: float | None

    def as_dict(self) -> dict[str, object]:
        """Проводная форма §14.7; ``min_confidence`` опускается при ``None``."""
        out: dict[str, object] = {
            "query": self.query,
            "top_k": self.top_k,
            "weights": dict(self.weights),
        }
        if self.min_confidence is not None:
            out["min_confidence"] = self.min_confidence
        return out


def _validate_top_k(raw: object) -> int:
    """Проверить ``top_k`` §14.7 / validate the §14.7 ``top_k`` field.

    Отсутствие даёт :data:`_DEFAULT_TOP_K`. Требуется целое (не ``bool``) в
    ``1..MAX_TOP_K``, иначе :class:`SearchValidationError`.
    """
    if raw is None:
        return _DEFAULT_TOP_K
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise SearchValidationError(f"top_k must be an integer, got {raw!r}")
    if not 1 <= raw <= MAX_TOP_K:
        raise SearchValidationError(f"top_k must be within 1..{MAX_TOP_K}, got {raw!r}")
    return raw


def _validate_weights(raw: object) -> dict[str, float]:
    """Проверить ``weights`` §14.7 / validate the §14.7 hybrid ``weights``.

    Отсутствие даёт пустой dict (сигнал «веса по умолчанию» на слое поиска).
    Каждый вес должен быть неотрицательным числом, а сумма непустых весов —
    строго положительной, иначе :class:`SearchValidationError`.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise SearchValidationError("weights must be a mapping or omitted")
    weights: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SearchValidationError(f"weight {key!r} must be a number, got {value!r}")
        weight = float(value)
        if weight < 0.0:
            raise SearchValidationError(f"weight {key!r} must be >= 0, got {weight!r}")
        weights[str(key)] = weight
    if weights and sum(weights.values()) <= 0.0:
        raise SearchValidationError("weights must have a positive sum")
    return weights


def _validate_min_confidence(raw: object) -> float | None:
    """Проверить ``min_confidence`` §14.7 / validate the §14.7 ``min_confidence``.

    Отсутствие или ``None`` даёт ``None`` (нет порога). Иначе требуется число
    в ``[0, 1]``, иначе :class:`SearchValidationError`.
    """
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise SearchValidationError(f"min_confidence must be a number, got {raw!r}")
    value = float(raw)
    if not 0.0 <= value <= 1.0:
        raise SearchValidationError(f"min_confidence must be within [0, 1], got {value!r}")
    return value


def validate_search_request(body: Mapping[str, object]) -> ValidatedSearchRequest:
    """Разобрать и валидировать §14.7 тело поиска / validate a §14.7 search body.

    ``query`` обязателен — непустая строка (после ``strip``). ``top_k`` целое в
    ``1..MAX_TOP_K`` (по умолчанию :data:`_DEFAULT_TOP_K`). ``weights`` —
    неотрицательные числа с положительной суммой. ``min_confidence`` — ``None``
    или число в ``[0, 1]``. Любое нарушение — :class:`SearchValidationError`.

    ``query`` must be a non-empty string; ``top_k`` an integer in
    ``1..MAX_TOP_K`` (default 10); each weight ``>= 0`` with a positive sum; and
    ``min_confidence`` in ``[0, 1]`` when present. Otherwise raises.
    """
    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        raise SearchValidationError("query must be a non-empty string")
    return ValidatedSearchRequest(
        query=query,
        top_k=_validate_top_k(body.get("top_k")),
        weights=_validate_weights(body.get("weights")),
        min_confidence=_validate_min_confidence(body.get("min_confidence")),
    )
