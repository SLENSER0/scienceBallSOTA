"""Opaque cursor pagination (§14.12).

Непрозрачная (opaque) курсорная пагинация на чистом stdlib: полезная нагрузка
``{"o": offset, ...extra}`` сериализуется в JSON и кодируется в urlsafe base64,
поэтому клиент видит только матовый токен и не может «угадать» смещение.

Opaque cursor pagination built only on the standard library. A payload of
``{"o": offset, ...extra}`` is JSON-serialized and wrapped in urlsafe base64, so
the client receives a matte token instead of a guessable offset.

* :class:`InvalidCursor`  — raised by :func:`decode_cursor` on malformed input.
* :func:`encode_cursor`   — offset (+ optional extras) → opaque token.
* :func:`decode_cursor`   — opaque token → payload dict (validated).
* :func:`next_cursor`     — token for the next page, or ``None`` at the end.
* :class:`PageMeta`       — frozen pagination descriptor with :meth:`as_dict`.
* :func:`paginate_meta`   — ready-made ``{offset, limit, total, ...}`` envelope.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any


class InvalidCursor(ValueError):
    """Курсор повреждён или не распознан / cursor is malformed (§14.12)."""


def encode_cursor(offset: int, *, extra: dict[str, Any] | None = None) -> str:
    """Собрать непрозрачный курсор из ``offset`` (+ ``extra``) (§14.12).

    Payload is ``{"o": offset, ...extra}`` — the offset is authoritative and
    always wins over an ``extra`` that happens to carry ``"o"``. The JSON is
    encoded as urlsafe base64 with the ``=`` padding stripped, yielding a
    compact matte token. ``offset`` must be a non-negative integer.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    payload: dict[str, Any] = dict(extra or {})
    payload["o"] = offset
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Разобрать непрозрачный курсор обратно в payload-словарь (§14.12).

    Обратная операция к :func:`encode_cursor`: восстанавливает исходный
    ``{"o": offset, ...extra}``. Любой сбой — пустая строка, не-base64, не-JSON,
    отсутствие/некорректный ``"o"`` — поднимает :class:`InvalidCursor`.
    """
    if not isinstance(cursor, str) or not cursor:
        raise InvalidCursor("cursor must be a non-empty string")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:  # binascii.Error / JSONDecodeError / Unicode* all subclass it
        raise InvalidCursor(f"malformed cursor: {cursor!r}") from exc
    if not isinstance(data, dict) or "o" not in data:
        raise InvalidCursor("cursor payload is missing the offset key 'o'")
    offset = data["o"]
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise InvalidCursor("cursor offset must be a non-negative integer")
    return data


def next_cursor(offset: int, limit: int, total: int) -> str | None:
    """Курсор следующей страницы или ``None``, если страниц больше нет (§14.12).

    Следующее смещение — ``offset + limit``; если оно достигает или превышает
    ``total``, текущая страница последняя и возвращается ``None``. ``limit``
    обязан быть положительным.
    """
    if limit <= 0:
        raise ValueError("limit must be >= 1")
    next_offset = offset + limit
    if next_offset >= total:
        return None
    return encode_cursor(next_offset)


@dataclass(frozen=True, slots=True)
class PageMeta:
    """Неизменяемый дескриптор одной страницы выборки (§14.12).

    Immutable pagination descriptor. ``next_cursor`` is the opaque token for the
    following page (``None`` on the last one) and ``has_more`` mirrors it —
    ``has_more`` is exactly ``next_cursor is not None``.
    """

    offset: int
    limit: int
    total: int
    next_cursor: str | None
    has_more: bool

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление страницы / wire envelope (§14.12)."""
        return {
            "offset": self.offset,
            "limit": self.limit,
            "total": self.total,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
        }


def paginate_meta(offset: int, limit: int, total: int) -> dict[str, Any]:
    """Собрать метаданные пагинации ``{offset, limit, total, ...}`` (§14.12).

    Convenience wrapper: computes :func:`next_cursor` once and derives
    ``has_more`` from it, returning the :class:`PageMeta` envelope as a dict so
    the two flags can never disagree.
    """
    nxt = next_cursor(offset, limit, total)
    return PageMeta(
        offset=offset,
        limit=limit,
        total=total,
        next_cursor=nxt,
        has_more=nxt is not None,
    ).as_dict()
