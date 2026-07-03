"""ETag computation and conditional-request caching (§14.17).

Детерминированные ETag-и на чистом stdlib: :func:`compute_etag` хеширует тело
ответа (str или bytes) в устойчивый sha256 и оборачивает его в кавычки по
RFC 7232, :func:`not_modified` реализует слабое сравнение заголовка
``If-None-Match`` (поддержка ``*``, списка через запятую и префикса ``W/``), а
:func:`cache_headers` собирает пару ``{ETag, Cache-Control}``.

Deterministic ETags on the standard library only. :func:`compute_etag` hashes a
response body (str or bytes) into a stable sha256 wrapped in RFC 7232 quotes,
:func:`not_modified` performs weak comparison of an ``If-None-Match`` header
(handling ``*``, comma lists and the ``W/`` weak prefix), and
:func:`cache_headers` assembles the ``{ETag, Cache-Control}`` pair.

* :func:`compute_etag`  — body → quoted, deterministic strong ETag.
* :func:`not_modified`  — ``If-None-Match`` value vs current ETag → 304 or not.
* :class:`CacheHeaders` — frozen ``{ETag, Cache-Control}`` pair with :meth:`as_dict`.
* :func:`cache_headers` — ready-made response-header dict.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


def compute_etag(body: str | bytes) -> str:
    """Устойчивый ETag тела ответа как ``"<sha256-hex>"`` (§14.17).

    ``body`` принимается строкой (кодируется в UTF-8) или байтами. Одинаковое
    содержимое всегда даёт одинаковый токен, а любое изменение байтов — новый;
    результат — 64-символьный sha256 в кавычках (strong validator, RFC 7232).
    """
    raw = body.encode("utf-8") if isinstance(body, str) else body
    return f'"{hashlib.sha256(raw).hexdigest()}"'


def _normalize(tag: str) -> str:
    """Снять префикс ``W/`` и кавычки для слабого сравнения / weak-compare form."""
    tag = tag.strip()
    if tag.startswith("W/"):
        tag = tag[2:].strip()
    return tag.strip('"')


def not_modified(request_etag: str | None, current_etag: str) -> bool:
    """Совпадает ли ``If-None-Match`` с текущим ETag → отдавать 304 (§14.17).

    Реализует слабое сравнение RFC 7232: ``W/`` и кавычки игнорируются. ``*``
    совпадает с любым существующим представлением. ``request_etag`` может быть
    списком через запятую; ``None`` или пустая строка означают «нет условия» и
    дают ``False``.
    """
    if not request_etag:
        return False
    current = _normalize(current_etag)
    for candidate in request_etag.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if _normalize(candidate) == current:
            return True
    return False


@dataclass(frozen=True, slots=True)
class CacheHeaders:
    """Неизменяемая пара заголовков кэширования ответа (§14.17).

    Immutable response cache-header pair. ``etag`` is the strong validator and
    ``cache_control`` is ``"public, max-age=<n>"`` derived from ``max_age``.
    """

    etag: str
    cache_control: str

    def as_dict(self) -> dict[str, Any]:
        """Заголовки как ``{ETag, Cache-Control}`` / wire headers (§14.17)."""
        return {"ETag": self.etag, "Cache-Control": self.cache_control}


def cache_headers(etag: str, max_age: int) -> dict[str, str]:
    """Собрать заголовки ``{ETag, Cache-Control}`` для ответа (§14.17).

    ``Cache-Control`` формируется как ``"public, max-age=<max_age>"``.
    ``max_age`` — время жизни в секундах, обязано быть неотрицательным.
    """
    if max_age < 0:
        raise ValueError("max_age must be >= 0")
    return CacheHeaders(
        etag=etag,
        cache_control=f"public, max-age={max_age}",
    ).as_dict()
