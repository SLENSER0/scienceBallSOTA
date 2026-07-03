"""§4.7 in-process embedding cache — content-hashed LRU over text→vector (pure python).

Эмбеддинг одного и того же текста (запрос, повторяющийся чанк, повторная выборка)
считается моделью заново без нужды: :func:`~kg_retrievers.embeddings.embed` — самая
дорогая операция в цепочке поиска. Этот модуль кэширует уже посчитанные векторы в
памяти процесса, ключуя их по **контент-хэшу** самого текста (sha256), а не по позиции
или порядковому id — поэтому один и тот же текст всегда попадает в одну ячейку, даже
если пришёл из другого документа.

:class:`EmbeddingCache` — фиксированного размера LRU (least-recently-used): при
переполнении ``maxsize`` вытесняется наименее недавно использованная запись, так что
объём памяти ограничен сверху. Учёт попаданий/промахов (:meth:`stats`) считается как
для «сырых» :meth:`get`, так и для :meth:`get_or_compute` — единственной точки, где
вектор вычисляется лениво через переданную функцию и сразу кладётся в кэш.

Снимок счётчиков отдаётся неизменяемым frozen dataclass :class:`CacheStats` с проекцией
:meth:`~CacheStats.as_dict` в ``{hits, misses, size}``.

Pure python — no numpy, no model/store/graph/DB access: вектор вычисляет **переданная**
функция; кэш лишь хранит и вытесняет. Kuzu note: custom node props are NOT queryable
columns — вызывающий RETURN'ит базовые колонки и читает остальное через ``get_node()``
перед тем, как отдавать текст на эмбеддинг сюда.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Вектор эмбеддинга — плоский список float (§4, 384d MiniLM), внутри хранится tuple.
Vector = list[float]

# Дефолтный потолок LRU (§4.7): столько уникальных текстов держим в памяти процесса.
DEFAULT_MAXSIZE = 1024


def content_key(text: str) -> str:
    """Content-hash key for ``text`` — sha256 hex of its UTF-8 bytes (§4.7).

    Один и тот же текст → один и тот же ключ (детерминированно, без учёта позиции);
    например ``content_key("abc")`` начинается на ``ba7816bf`` (эталон sha256).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheStats:
    """Immutable snapshot of cache counters (§4.7): hits, misses, current size.

    ``hits``/``misses`` — накопленные с момента создания или последнего
    :meth:`EmbeddingCache.clear`; ``size`` — число живых записей на момент снимка.
    """

    hits: int
    misses: int
    size: int

    @property
    def lookups(self) -> int:
        """Total lookups seen = ``hits + misses`` (§4.7)."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Fraction of lookups that hit in ``[0, 1]``; ``0.0`` when no lookups yet (§4.7)."""
        total = self.lookups
        return self.hits / total if total else 0.0

    def as_dict(self) -> dict[str, int]:
        """JSON-ready projection exactly ``{hits, misses, size}`` (§4.7 stats contract)."""
        return {"hits": self.hits, "misses": self.misses, "size": self.size}


class EmbeddingCache:
    """Content-hashed, fixed-size LRU cache mapping text → embedding vector (§4.7).

    ``maxsize`` — жёсткий потолок числа записей (LRU-вытеснение при переполнении).
    Ключи — контент-хэши (:func:`content_key`), поэтому одинаковый текст делит одну
    ячейку. Векторы копируются на входе и на выходе (хранятся как ``tuple``), так что
    внешняя мутация исходного списка не портит кэш и наоборот.
    """

    __slots__ = ("_hits", "_maxsize", "_misses", "_store")

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        if maxsize < 1:
            raise ValueError(f"maxsize must be >= 1, got {maxsize!r}")
        self._maxsize: int = maxsize
        # LRU-порядок: самый правый — недавно использованный, самый левый — жертва.
        self._store: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0

    @property
    def maxsize(self) -> int:
        """Configured upper bound on the number of cached entries (§4.7)."""
        return self._maxsize

    def __len__(self) -> int:
        """Current number of live entries (never exceeds :attr:`maxsize`) (§4.7)."""
        return len(self._store)

    def __contains__(self, text: str) -> bool:
        """Membership test by content-hash; does **not** count as a hit/miss (§4.7)."""
        return content_key(text) in self._store

    def get(self, text: str) -> Vector | None:
        """Return the cached vector for ``text`` or ``None`` on miss (§4.7).

        Попадание помечает запись как недавно использованную (перенос в конец LRU) и
        инкрементит ``hits``; промах инкрементит ``misses`` и возвращает ``None``.
        Отдаётся свежая копия-``list`` — мутация результата не трогает кэш.
        """
        key = content_key(text)
        vec = self._store.get(key)
        if vec is None:
            self._misses += 1
            return None
        self._store.move_to_end(key)  # mark most-recently-used
        self._hits += 1
        return list(vec)

    def put(self, text: str, vector: Sequence[float]) -> None:
        """Store ``vector`` under ``text``'s content key, evicting LRU if over cap (§4.7).

        Повторный ``put`` того же текста обновляет вектор и освежает LRU-позицию (не
        плодит дубли). После вставки при ``len > maxsize`` вытесняется наименее недавно
        использованная запись, так что размер ограничен сверху.
        """
        key = content_key(text)
        self._store[key] = tuple(float(x) for x in vector)  # copy → immutable snapshot
        self._store.move_to_end(key)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)  # evict least-recently-used

    def get_or_compute(self, text: str, fn: Callable[[str], Sequence[float]]) -> Vector:
        """Return cached vector for ``text`` or compute via ``fn(text)`` then cache it (§4.7).

        На попадании ``fn`` **не** вызывается (учитывается ``hit``); на промахе
        (учитывается ``miss``) вызывается ``fn(text)``, результат кладётся в кэш и
        возвращается копией. Единственная точка ленивого вычисления вектора.
        """
        cached = self.get(text)  # counts the hit/miss
        if cached is not None:
            return cached
        computed = fn(text)
        self.put(text, computed)
        return list(computed)

    def stats(self) -> dict[str, int]:
        """Return counters as ``{hits, misses, size}`` (§4.7); see :class:`CacheStats`."""
        return self.snapshot().as_dict()

    def snapshot(self) -> CacheStats:
        """Immutable :class:`CacheStats` of the current counters and size (§4.7)."""
        return CacheStats(hits=self._hits, misses=self._misses, size=len(self._store))

    def clear(self) -> None:
        """Drop all entries and reset hit/miss counters to a fresh state (§4.7)."""
        self._store.clear()
        self._hits = 0
        self._misses = 0


__all__ = ["DEFAULT_MAXSIZE", "CacheStats", "EmbeddingCache", "Vector", "content_key"]
