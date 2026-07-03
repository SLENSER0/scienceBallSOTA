"""Multilingual embeddings (§4 / ADR-0006, OSS models only).

Two backends behind one API:

* **fastembed** (ONNX, no torch) for models fastembed ships — fast, light.
* **sentence-transformers** for any other HF model (e.g. IBM Granite
  ``granite-embedding-*-multilingual-r2``) that fastembed does not package.

The backend is chosen automatically from ``settings.embedding_model``; the vector
``dim()`` is read from the loaded model so a model swap can't silently mismatch the
Qdrant collection. Lazy singleton — the model loads once per process.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable

from kg_common import get_logger, get_settings

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


def embed(texts: Iterable[str]) -> list[list[float]]:
    docs = [t if t.strip() else " " for t in texts]
    if not docs:
        return []
    return _model().encode(docs)


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
