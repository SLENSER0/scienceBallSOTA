"""API response envelope helpers (§14.13).

Единый конверт ответа API на чистом stdlib: любое тело оборачивается в стабильную
тройку ключей ``{data, meta, request_id}``, поэтому клиент всегда видит одну и ту
же форму — payload в ``data``, служебные метаданные в ``meta`` и сквозной
идентификатор запроса в ``request_id``. Списочный вариант кладёт в ``data``
подконверт ``{items, total}`` и переиспользует ту же оболочку.

A single API response envelope built only on the standard library. Every body is
wrapped in the stable key triple ``{data, meta, request_id}``, so the client
always sees the same shape — the payload under ``data``, service metadata under
``meta`` and a request-scoped id under ``request_id``. The list variant nests an
``{items, total}`` sub-envelope under ``data`` and reuses the same wrapper.

* :class:`Envelope`       — frozen ``{data, meta, request_id}`` with :meth:`as_dict`.
* :func:`ok_envelope`     — wrap an arbitrary payload (+ optional ``meta``/id).
* :func:`list_envelope`   — wrap ``items`` + ``total`` under a list sub-envelope.
* :func:`with_request_id` — return a copy of a body with ``request_id`` set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Envelope:
    """Неизменяемый конверт ответа ``{data, meta, request_id}`` (§14.13).

    Immutable response envelope. ``data`` carries the payload, ``meta`` holds
    optional service metadata (``None`` when absent) and ``request_id`` threads a
    request-scoped identifier (``None`` when unset). :meth:`as_dict` always emits
    the three keys, so the wire shape stays stable regardless of the values.
    """

    data: Any
    meta: dict[str, Any] | None
    request_id: str | None

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление конверта / wire envelope (§14.13)."""
        return {
            "data": self.data,
            "meta": self.meta,
            "request_id": self.request_id,
        }


def ok_envelope(
    data: Any,
    *,
    request_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Обернуть payload в конверт ``{data, meta, request_id}`` (§14.13).

    Wrap an arbitrary ``data`` payload. ``meta`` and ``request_id`` are optional
    and default to ``None``; both keys are always present in the result so the
    envelope shape never varies. ``data`` is stored as-is — it is not copied.
    """
    return Envelope(data=data, meta=meta, request_id=request_id).as_dict()


def list_envelope(
    items: list[Any],
    total: int,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Обернуть список в конверт со счётчиком ``{items, total}`` (§14.13).

    Build a list response: ``data`` becomes the sub-envelope ``{"items": items,
    "total": total}`` and the whole thing is wrapped by :func:`ok_envelope`.
    ``total`` is the full count before any pagination and is independent of
    ``len(items)`` (the current page size).
    """
    return ok_envelope({"items": items, "total": total}, request_id=request_id)


def with_request_id(body: dict[str, Any], rid: str) -> dict[str, Any]:
    """Вернуть копию тела с проставленным ``request_id`` (§14.13).

    Return a shallow copy of ``body`` with ``request_id`` set to ``rid``; the
    input mapping is never mutated. Any pre-existing ``request_id`` is overwritten
    and all other keys are preserved unchanged.
    """
    return {**body, "request_id": rid}
