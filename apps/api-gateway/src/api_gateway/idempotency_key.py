"""Idempotency-Key handling for mutating POSTs: replay vs conflict (§14.10/14.12).

Реализует обработку заголовка ``Idempotency-Key`` для мутирующих POST-запросов
согласно §14.10/§14.12: клиент присылает ключ вместе с запросом, а сервер должен
выполнить операцию ровно один раз. Повтор с тем же ключом и тем же телом отдаёт
сохранённый ответ (replay); повтор с тем же ключом, но другим телом — это ошибка
(conflict). Чистый stdlib, без FastAPI.

Implements ``Idempotency-Key`` handling for mutating POST requests per
§14.10/§14.12: a client sends a key with the request and the server must perform
the operation exactly once. A repeat with the same key and the same request body
returns the stored response (a *replay*); a repeat with the same key but a
different body is an error (a *conflict*). Pure standard library, no FastAPI:

* :class:`IdempotencyRecord` — frozen (key, fingerprint, response, created_at).
* :func:`is_valid_key`       — non-empty printable-ASCII key, length ``<= 200``.
* :func:`fingerprint`        — sha256 hex over ``method`` + ``path`` + ``body``.
* :class:`IdempotencyStore`  — in-memory register → ``stored``/``replay``/``conflict``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Максимальная длина ключа идемпотентности / max Idempotency-Key length (§14.10).
_MAX_KEY_LEN = 200


@dataclass(frozen=True)
class IdempotencyRecord:
    """Неизменяемая запись об обработанном ключе идемпотентности (§14.10).

    Frozen record of one processed idempotency key: the client ``key``, the
    ``request_fingerprint`` that pinned this key to a specific request, the
    stored ``response`` returned on replay, and the ISO-8601 ``created_at``
    timestamp of first registration.
    """

    key: str
    request_fingerprint: str
    response: Any
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {
            "key": self.key,
            "request_fingerprint": self.request_fingerprint,
            "response": self.response,
            "created_at": self.created_at,
        }


def is_valid_key(key: str) -> bool:
    """Валиден ли ключ идемпотентности / idempotency-key validity (§14.10).

    Returns ``True`` when ``key`` is a non-empty printable-ASCII string no longer
    than ``200`` characters; otherwise ``False``. An empty key, an over-long key
    (length ``> 200``), or a key containing a control or non-ASCII character is
    rejected.
    """
    if not key or len(key) > _MAX_KEY_LEN:
        return False
    return all(0x20 <= ord(ch) <= 0x7E for ch in key)


def fingerprint(method: str, path: str, body: bytes) -> str:
    """Отпечаток запроса sha256-hex / request fingerprint (§14.10).

    Computes a deterministic ``sha256`` hex digest over the request ``method``,
    ``path`` and raw ``body`` bytes. Two requests with identical method, path and
    body share a fingerprint; any difference yields a different digest. Used by
    :class:`IdempotencyStore` to tell a legitimate replay from a conflict.
    """
    hasher = hashlib.sha256()
    hasher.update(method.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(path.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(body)
    return hasher.hexdigest()


class IdempotencyStore:
    """In-memory реестр ключей идемпотентности / idempotency registry (§14.10).

    Maps each idempotency ``key`` to the :class:`IdempotencyRecord` created on its
    first use. :meth:`register` decides the outcome for a ``(key, fingerprint)``
    pair: ``stored`` on first use, ``replay`` when the key repeats with the same
    fingerprint, or ``conflict`` when it repeats with a different fingerprint.
    Not thread-safe; intended for single-process gateway use behind the API lock.
    """

    def __init__(self) -> None:
        """Пустой реестр / start with an empty key → record mapping."""
        self._records: dict[str, IdempotencyRecord] = {}

    def register(
        self,
        key: str,
        request_fingerprint: str,
        response: Any,
    ) -> tuple[str, IdempotencyRecord]:
        """Зарегистрировать ключ и вернуть исход / register key (§14.10).

        Returns a ``(outcome, record)`` tuple:

        * ``("stored", record)``   — ``key`` is new; ``response`` is saved and the
          fresh :class:`IdempotencyRecord` returned.
        * ``("replay", record)``   — ``key`` already exists with the **same**
          ``request_fingerprint``; the **original** stored record (and its
          response) is returned and the incoming ``response`` is ignored.
        * ``("conflict", record)`` — ``key`` already exists with a **different**
          ``request_fingerprint``; the original record is returned so the caller
          can surface a ``409``-style error. No state is mutated.
        """
        existing = self._records.get(key)
        if existing is not None:
            if existing.request_fingerprint == request_fingerprint:
                return "replay", existing
            return "conflict", existing
        record = IdempotencyRecord(
            key=key,
            request_fingerprint=request_fingerprint,
            response=response,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._records[key] = record
        return "stored", record

    def get(self, key: str) -> IdempotencyRecord | None:
        """Запись по ключу или ``None`` / stored record for ``key`` (§14.10)."""
        return self._records.get(key)
