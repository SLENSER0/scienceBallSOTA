"""Embedding feature for ER blocking/comparison (§8.3).

Optional: uses fastembed (already a kg_retrievers dep) when installed. Falls
back to a deterministic hashing embedding so blocking-by-similarity is testable
without the model download. Vectors are L2-normalized (cosine == dot).
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

_DIM = 256

try:  # pragma: no cover - model path exercised only when fastembed present
    from fastembed import TextEmbedding

    _HAS_FASTEMBED = True
except Exception:  # pragma: no cover
    TextEmbedding = None
    _HAS_FASTEMBED = False


@lru_cache(maxsize=1)
def _model():  # pragma: no cover - network/model dependent
    return TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


def _hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-tokens hashing embedding (fallback)."""
    vec = [0.0] * _DIM
    for tok in text.split():
        h = int(hashlib.sha1(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % _DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_text(text: str | None, *, use_model: bool = False) -> list[float]:
    """Return an L2-normalized embedding for *text*.

    ``use_model=True`` uses fastembed (1024/384-dim depending on model); default
    uses the deterministic fallback so tests are hermetic.
    """
    text = (text or "").strip()
    if not text:
        return [0.0] * _DIM
    if use_model and _HAS_FASTEMBED:  # pragma: no cover
        vec = list(next(iter(_model().embed([text]))))
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [float(v) / norm for v in vec]
    return _hash_embed(text)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=False))))
