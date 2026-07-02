"""Multilingual embeddings via fastembed (§4 / ADR-0006, Apache-2.0 model).

``sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`` (384d) gives
strong RU↔EN cross-lingual similarity. Lazy singleton so the model loads once.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable

from kg_common import get_logger, get_settings

_log = get_logger("embeddings")


@functools.lru_cache(maxsize=1)
def _model():  # type: ignore[no-untyped-def]
    from fastembed import TextEmbedding

    name = get_settings().embedding_model
    _log.info("embeddings.load", model=name)
    return TextEmbedding(model_name=name)


def embed(texts: Iterable[str]) -> list[list[float]]:
    docs = [t if t.strip() else " " for t in texts]
    if not docs:
        return []
    return [vec.tolist() for vec in _model().embed(docs)]


def embed_one(text: str) -> list[float]:
    out = embed([text])
    return out[0] if out else []


def dim() -> int:
    return get_settings().embedding_dim
