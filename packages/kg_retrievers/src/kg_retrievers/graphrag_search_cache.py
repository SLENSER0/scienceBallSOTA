"""§11.7 GraphRAG global-search result cache — TTL over (query, build, level) keys.

Глобальный (community-level) GraphRAG-поиск — дорогая операция: запрос прогоняется по
сводкам сообществ выбранного уровня иерархии, и один и тот же вопрос на одной и той же
сборке графа даёт один и тот же ответ. Этот модуль кэширует результат такого поиска в
памяти процесса, ключуя его тройкой :class:`CacheKey` ``(query_hash, build_version,
level)``:

* ``query_hash`` — sha256-хэш **нормализованного** текста запроса (lowercase + strip),
  усечённый до 16 hex-символов, так что ``"Overview "`` и ``"overview"`` делят ячейку;
* ``build_version`` — версия сборки графа: при перестроении графа старые ответы обязаны
  промахиваться, поэтому разные версии **никогда** не сталкиваются;
* ``level`` — уровень иерархии сообществ (int): разные уровни — разные ячейки.

:class:`GlobalSearchCache` — TTL-кэш: запись живёт ``ttl_seconds`` по часам, которые
подаются извне как ``clock`` (callable → float секунд), что делает истечение полностью
детерминированным в тестах. :meth:`~GlobalSearchCache.get` на протухшей записи удаляет
её и считает как промах; :meth:`~GlobalSearchCache.evict_expired` подметает все
истёкшие разом и возвращает их число. Счётчики отдаются через
:meth:`~GlobalSearchCache.stats` как ``{hits, misses, size}``.

Pure python — no model/store/graph/DB access. Kuzu note: custom node props are NOT
queryable columns — вызывающий RETURN'ит базовые колонки и читает остальное через
``get_node()`` перед тем, как формировать текст запроса для ключа здесь.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Длина усечённого sha256-хэша нормализованного запроса (§11.7): 16 hex-символов.
QUERY_HASH_LEN = 16


def normalize_query(query: str) -> str:
    """Normalize ``query`` for hashing: strip surrounding whitespace, then lowercase (§11.7).

    ``"Overview "`` и ``"overview"`` → одинаковая нормальная форма ``"overview"``, поэтому
    их ключи совпадают; регистр и краевые пробелы не влияют на попадание в кэш.
    """
    return query.strip().lower()


@dataclass(frozen=True)
class CacheKey:
    """Immutable cache key for a GraphRAG global search (§11.7).

    Тройка ``(query_hash, build_version, level)`` однозначно адресует ответ: хэш
    нормализованного запроса, версия сборки графа и уровень иерархии сообществ.
    ``level`` — всегда ``int`` (см. :meth:`as_dict`).
    """

    query_hash: str
    build_version: str
    level: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready projection ``{query_hash, build_version, level}`` (§11.7).

        ``as_dict()["level"]`` — всегда ``int`` (тип поля не меняется при проекции).
        """
        return {
            "query_hash": self.query_hash,
            "build_version": self.build_version,
            "level": self.level,
        }

    def to_str(self) -> str:
        """Flat string form joining the three fields with ``:`` (§11.7).

        Например ``CacheKey("abcd", "v1", 2).to_str()`` == ``"abcd:v1:2"`` — стабильный
        человекочитаемый идентификатор ячейки.
        """
        return f"{self.query_hash}:{self.build_version}:{self.level}"


def make_key(query: str, build_version: str, level: int) -> CacheKey:
    """Build a :class:`CacheKey` for ``query`` at ``build_version``/``level`` (§11.7).

    Запрос нормализуется (:func:`normalize_query`) и хэшируется sha256; берутся первые
    :data:`QUERY_HASH_LEN` hex-символов. Поэтому ``make_key("Overview ", "v1", 2)`` и
    ``make_key("overview", "v1", 2)`` равны, а ``level=1`` даёт другой ключ.
    """
    digest = hashlib.sha256(normalize_query(query).encode("utf-8")).hexdigest()
    return CacheKey(query_hash=digest[:QUERY_HASH_LEN], build_version=build_version, level=level)


@dataclass
class _Entry:
    """Internal cache slot: stored value plus its insertion timestamp (§11.7)."""

    value: Any
    inserted_at: float


class GlobalSearchCache:
    """In-process TTL cache for GraphRAG global-search results (§11.7).

    Запись живёт ``ttl_seconds`` относительно ``clock()`` на момент :meth:`put`; при
    ``clock() - inserted_at > ttl`` она считается протухшей. ``clock`` инъектируется
    (по умолчанию :func:`time.monotonic`), что делает истечение детерминированным в
    тестах. Счётчики ``hits``/``misses`` копятся с момента создания или :meth:`clear`.
    """

    __slots__ = ("_clock", "_hits", "_misses", "_store", "_ttl")

    def __init__(self, ttl_seconds: int, clock: Callable[[], float] = time.monotonic) -> None:
        if ttl_seconds < 0:
            raise ValueError(f"ttl_seconds must be >= 0, got {ttl_seconds!r}")
        self._ttl: float = float(ttl_seconds)
        self._clock: Callable[[], float] = clock
        self._store: dict[CacheKey, _Entry] = {}
        self._hits: int = 0
        self._misses: int = 0

    @property
    def ttl_seconds(self) -> float:
        """Configured time-to-live in seconds for each entry (§11.7)."""
        return self._ttl

    def __len__(self) -> int:
        """Number of stored slots, including any not-yet-swept expired ones (§11.7)."""
        return len(self._store)

    def _is_expired(self, entry: _Entry, now: float) -> bool:
        """True when ``now - entry.inserted_at`` strictly exceeds the TTL (§11.7)."""
        return (now - entry.inserted_at) > self._ttl

    def get(self, key: CacheKey) -> Any | None:
        """Return the value for ``key`` or ``None`` on miss/expiry (§11.7).

        Промах (нет ключа) или протухшая запись → ``None`` и инкремент ``misses``;
        протухшая запись при этом удаляется на месте. Живое попадание → значение и
        инкремент ``hits``.
        """
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if self._is_expired(entry, self._clock()):
            del self._store[key]  # lazily drop the stale slot
            self._misses += 1
            return None
        self._hits += 1
        return entry.value

    def put(self, key: CacheKey, value: Any) -> None:
        """Store ``value`` under ``key``, stamping insertion time from ``clock()`` (§11.7).

        Повторный ``put`` того же ключа заменяет значение и освежает метку времени (TTL
        отсчитывается заново), не плодя дублей.
        """
        self._store[key] = _Entry(value=value, inserted_at=self._clock())

    def evict_expired(self) -> int:
        """Drop every expired entry and return how many were removed (§11.7).

        Не трогает счётчики ``hits``/``misses`` — это уборка, а не поиск; ``size`` после
        неё отражает только живые записи.
        """
        now = self._clock()
        stale = [key for key, entry in self._store.items() if self._is_expired(entry, now)]
        for key in stale:
            del self._store[key]
        return len(stale)

    def stats(self) -> dict[str, int]:
        """Return counters as ``{hits, misses, size}`` (§11.7).

        ``size`` считает живые (не протухшие) записи на момент вызова — протухшие
        исключаются, но из хранилища не удаляются (используйте :meth:`evict_expired`).
        """
        now = self._clock()
        live = sum(1 for entry in self._store.values() if not self._is_expired(entry, now))
        return {"hits": self._hits, "misses": self._misses, "size": live}

    def clear(self) -> None:
        """Drop all entries and reset hit/miss counters to a fresh state (§11.7)."""
        self._store.clear()
        self._hits = 0
        self._misses = 0


__all__ = [
    "QUERY_HASH_LEN",
    "CacheKey",
    "GlobalSearchCache",
    "make_key",
    "normalize_query",
]
