"""Multilingual embeddings (§4 / ADR-0006, OSS models only).

Two backends behind one API:

* **fastembed** (ONNX, no torch) for models fastembed ships — fast, light.
* **sentence-transformers** for any other HF model (e.g. IBM Granite
  ``granite-embedding-*-multilingual-r2``) that fastembed does not package.

The backend is chosen automatically from ``settings.embedding_model``; the vector
``dim()`` is read from the loaded model so a model swap can't silently mismatch the
Qdrant collection. Lazy singleton — the model loads once per process.

§4.7 caching — :func:`embed` is the most expensive step in the retrieval chain, so
every result is memoised by **content-hash** through a process-wide
:class:`~kg_retrievers.embedding_cache.EmbeddingCache`: identical texts (including
duplicates inside one call, or the fixed demo query set) skip the model forward pass
and collapse to an O(1) dict lookup. An *optional* on-disk layer (off by default,
enabled via ``KG_EMBED_DISK_CACHE``) persists vectors across process restarts, keyed
by content-hash inside a per-model namespace so a model swap can never return a stale
vector. Both layers are behavior-preserving: the model is deterministic per text and
``encode()`` has no cross-text context, so only *recompute* is skipped.
"""

from __future__ import annotations

import functools
import json
import os
import pathlib
import re
import sqlite3
import threading
from collections.abc import Iterable

from kg_common import get_logger, get_settings
from kg_retrievers.embedding_cache import EmbeddingCache, content_key

_log = get_logger("embeddings")


def _fastembed_supports(name: str) -> bool:
    try:
        from fastembed import TextEmbedding

        return any(m["model"] == name for m in TextEmbedding.list_supported_models())
    except Exception:
        return False


class _Backend:
    """A loaded embedding model exposing ``encode(texts) -> list[list[float]]``."""

    def __init__(self, name: str) -> None:
        self.name = name
        if _fastembed_supports(name):
            from fastembed import TextEmbedding

            self._kind = "fastembed"
            self._m = TextEmbedding(model_name=name)
        else:
            from sentence_transformers import SentenceTransformer

            self._kind = "sentence-transformers"
            self._m = SentenceTransformer(name)
        _log.info("embeddings.load", model=name, backend=self._kind)

    def encode(self, docs: list[str]) -> list[list[float]]:
        if self._kind == "fastembed":
            return [vec.tolist() for vec in self._m.embed(docs)]
        return [vec.tolist() for vec in self._m.encode(docs, normalize_embeddings=True)]


@functools.lru_cache(maxsize=1)
def _model() -> _Backend:
    return _Backend(get_settings().embedding_model)


# ---------------------------------------------------------------------------
# §4.7 in-process cache — process-wide, content-hashed, shared by embed()
# ---------------------------------------------------------------------------

# Единый на процесс LRU (самый горячий кэш): повторные тексты не гоняются через
# модель. Мутации/чтения OrderedDict сериализуем локом — embed() зовут из разных
# потоков FastAPI, а тяжёлый forward pass идёт ВНЕ лока (не сериализуем инференс).
_CACHE = EmbeddingCache()
_CACHE_LOCK = threading.Lock()


def embedding_cache() -> EmbeddingCache:
    """Return the process-wide embedding cache singleton (§4.7).

    Живёт на уровне модуля и делится между :func:`embed`/:func:`embed_one`; отдаётся в
    основном для интроспекции (``.stats()``) и сброса в тестах (``.clear()``).
    """
    return _CACHE


# ---------------------------------------------------------------------------
# §4.7 optional on-disk cache — survives restarts, off by default
# ---------------------------------------------------------------------------

_DISK_LOCK = threading.Lock()
_DISK_CACHE: _DiskCache | None = None
_DISK_CACHE_MODEL: str | None = None


def _slug(name: str) -> str:
    """Filesystem-safe slug of a model name (namespaces the on-disk store)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def _disk_enabled() -> bool:
    """``True`` iff ``KG_EMBED_DISK_CACHE`` is set truthy (default off → no I/O)."""
    return os.environ.get("KG_EMBED_DISK_CACHE", "").strip().lower() in {"1", "true", "yes", "on"}


def _disk_path(model_name: str) -> str:
    """SQLite path for ``model_name``; dir from ``KG_EMBED_DISK_CACHE_DIR`` or runtime_dir."""
    base = os.environ.get("KG_EMBED_DISK_CACHE_DIR", "").strip()
    if not base:
        base = str(pathlib.Path(get_settings().runtime_dir) / "embed_cache")
    pathlib.Path(base).mkdir(parents=True, exist_ok=True)
    return str(pathlib.Path(base) / f"embed_{_slug(model_name)}.sqlite")


class _DiskCache:
    """Content-hash-keyed SQLite persistence of ``text → vector`` (§4.7, off by default).

    Пережидает рестарты процесса: ключ — :func:`~kg_retrievers.embedding_cache.content_key`
    (sha256 текста), значение — вектор в JSON. Модель зашита в **имя файла** namespace,
    поэтому смена ``embedding_model`` открывает другой файл и устаревший вектор вернуться
    не может. PRIMARY KEY даёт индекс по ключу — чтение это один индексный select.
    """

    __slots__ = ("_conn", "_lock")

    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        # check_same_thread=False + own lock: одно соединение на процесс, доступ сериализован.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS vectors (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
        )
        self._conn.commit()

    def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        """Return ``{content_key: vector}`` for the subset of ``keys`` present on disk."""
        if not keys:
            return {}
        placeholders = ",".join("?" * len(keys))
        sql = f"SELECT k, v FROM vectors WHERE k IN ({placeholders})"  # keys are bound params
        with self._lock:
            rows = self._conn.execute(sql, keys).fetchall()
        return {k: json.loads(v) for k, v in rows}

    def put_many(self, items: list[tuple[str, list[float]]]) -> None:
        """Persist ``(content_key, vector)`` pairs (idempotent upsert), one transaction."""
        if not items:
            return
        payload = [(k, json.dumps([float(x) for x in v])) for k, v in items]
        with self._lock:
            self._conn.executemany("INSERT OR REPLACE INTO vectors (k, v) VALUES (?, ?)", payload)
            self._conn.commit()


def _disk_cache() -> _DiskCache | None:
    """Lazily-opened on-disk cache for the active model, or ``None`` when disabled.

    Reopened if ``embedding_model`` changed since last call, so the namespace always
    tracks the live model (guards against stale vectors after a swap).
    """
    if not _disk_enabled():
        return None
    global _DISK_CACHE, _DISK_CACHE_MODEL
    model_name = get_settings().embedding_model
    with _DISK_LOCK:
        if _DISK_CACHE is None or model_name != _DISK_CACHE_MODEL:
            _DISK_CACHE = _DiskCache(_disk_path(model_name))
            _DISK_CACHE_MODEL = model_name
        return _DISK_CACHE


def _compute(missing: list[str]) -> list[list[float]]:
    """Embed a de-duplicated ``missing`` list, aligned to its order (§4.7 miss path).

    Модель зовётся ровно одним батчем (single-batch свойство сохранено). Если включён
    on-disk слой — сперва читаем его, и через модель идёт лишь то, чего нет и на диске;
    свежие векторы дописываются обратно, чтобы пережить рестарт.
    """
    disk = _disk_cache()
    if disk is None:
        return _model().encode(missing)
    keys = [content_key(t) for t in missing]
    found = disk.get_many(keys)
    todo = [t for t, k in zip(missing, keys, strict=True) if k not in found]
    if todo:
        fresh = _model().encode(todo)
        disk.put_many([(content_key(t), v) for t, v in zip(todo, fresh, strict=True)])
        for t, v in zip(todo, fresh, strict=True):
            found[content_key(t)] = v
    return [found[k] for k in keys]


def embed(texts: Iterable[str]) -> list[list[float]]:
    """Embed ``texts`` → one vector per input, in input order (§4 / §4.7 cached).

    Кэшируем по контент-хэшу: одинаковые тексты (в т.ч. дубликаты внутри одного вызова,
    повторяющиеся запросы, неизменные описания сущностей при переиндексации) считаются
    моделью один раз, остальное берётся из процессного LRU за O(1). Модель вызывается
    ровно одним батчем на промахах — single-batch свойство сохранено.

    Behavior-preserving: модель детерминирована на тексте и не имеет кросс-текстового
    контекста, а каждой позиции отдаётся собственная копия-``list`` (как у ``encode()``),
    так что пропуск повторного счёта не меняет результат — только экономит forward pass.
    """
    docs = [t if t.strip() else " " for t in texts]
    if not docs:
        return []
    keys = [content_key(d) for d in docs]
    vectors: dict[str, list[float]] = {}  # content_key → computed/cached vector
    misses: list[str] = []  # unique miss texts, first-seen order (fed to the model once)
    queued: set[str] = set()  # miss keys already queued (dedup within this call)
    with _CACHE_LOCK:
        for doc, key in zip(docs, keys, strict=True):
            if key in vectors or key in queued:
                continue  # already resolved (hit) or already queued (duplicate miss)
            cached = _CACHE.get(doc)
            if cached is not None:
                vectors[key] = cached
            else:
                queued.add(key)
                misses.append(doc)
    if misses:
        computed = _compute(misses)  # ONE model batch (disk layer may shrink it further)
        with _CACHE_LOCK:
            for text, vec in zip(misses, computed, strict=True):
                _CACHE.put(text, vec)
                vectors[content_key(text)] = vec
    # Fresh list per position → distinct objects exactly like _model().encode() returns.
    return [list(vectors[key]) for key in keys]


def embed_one(text: str) -> list[float]:
    out = embed([text])
    return out[0] if out else []


@functools.lru_cache(maxsize=1)
def dim() -> int:
    """Vector dimension of the active model (probed once, falls back to config)."""
    try:
        return len(embed_one("dimension probe"))
    except Exception:
        return get_settings().embedding_dim
