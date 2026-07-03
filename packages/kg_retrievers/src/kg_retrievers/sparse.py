"""Sparse lexical vectors — SPLADE-lite for the embedded profile (§4.4).

§4.4 (dense / sparse / multivector embeddings) specifies a sparse lexical
channel via ``fastembed`` SPLADE/BM25 for the server profile. On the **embedded
profile** we cannot pull a torch-backed model, so this module provides a
transparent, dependency-free stand-in: a term-frequency sparse vector over
folded RU/EN tokens, plus an inverted-index :class:`SparseIndex` that adds an
inverse-document-frequency (IDF, обратная документная частота) weighting learned
from the corpus it is fed.

A *sparse vector* here is a plain ``dict[token, float]`` — most tokens absent,
each present token carrying a **log-TF** weight ``1 + ln(tf)`` (saturating term
frequency, частота термина). Only content tokens survive: a token must be at
least :data:`MIN_TOKEN_LEN` characters and not a RU/EN stopword (стоп-слово), so
function words and short stray fragments drop out. Everything is deterministic:
tokenisation folds through :func:`kg_common.canonical_key`, dict order is
insertion order, and ranking ties break on ``doc_id``.

The IDF used by :class:`SparseIndex` is the smoothed form
``ln((N + 1) / (df + 1))`` where ``N`` is the corpus size and ``df`` the number
of documents containing the token. It is always ``>= 0`` and collapses to exactly
``0`` for a term present in **every** document (``df == N``) — such a term adds
no discriminating signal and is fully down-weighted at search time.
"""

from __future__ import annotations

import math
import re

from kg_common import canonical_key

# A content token must be at least this long; shorter fragments (RU «и/в/на»,
# EN «a/of/to») carry no lexical signal and are dropped (§4.4).
MIN_TOKEN_LEN: int = 3

# RU/EN function words (стоп-слова). Short ones are already removed by the
# length gate; the set targets the length->=3 words that would otherwise pass.
STOPWORDS: frozenset[str] = frozenset(
    {
        # English
        "the",
        "and",
        "are",
        "for",
        "was",
        "were",
        "this",
        "that",
        "with",
        "from",
        "have",
        "has",
        "had",
        "not",
        "but",
        "its",
        "into",
        "than",
        "then",
        "them",
        "they",
        "which",
        "while",
        "will",
        "would",
        "can",
        "could",
        "been",
        "being",
        "also",
        "such",
        "per",
        "any",
        "all",
        "our",
        "your",
        "his",
        "her",
        "who",
        "how",
        "why",
        "did",
        "does",
        # Russian
        "для",
        "что",
        "как",
        "это",
        "или",
        "если",
        "все",
        "его",
        "они",
        "она",
        "оно",
        "был",
        "была",
        "было",
        "были",
        "при",
        "над",
        "под",
        "без",
        "про",
        "чтобы",
        "когда",
        "где",
        "кто",
        "том",
        "тем",
        "той",
        "эта",
        "эти",
        "этот",
        "между",
        "после",
        "перед",
        "тоже",
        "также",
        "уже",
        "еще",
    }
)

# Token = maximal run of RU/EN letters or digits. ``canonical_key`` has already
# lower-cased, NFKC-normalised and turned separators into spaces (§4.4).
_TOKEN_RE = re.compile(r"[0-9a-zа-яё]+")


def fold_tokens(text: str) -> list[str]:
    """Fold ``text`` to a deterministic list of content tokens (§4.4).

    Normalises via :func:`kg_common.canonical_key` (NFKC + lower + separator
    collapse, Cyrillic preserved), then keeps runs of letters/digits that are at
    least :data:`MIN_TOKEN_LEN` long and not a :data:`STOPWORDS` member. RU and
    EN tokens are treated identically.
    """
    folded = canonical_key(text)
    return [
        tok
        for tok in _TOKEN_RE.findall(folded)
        if len(tok) >= MIN_TOKEN_LEN and tok not in STOPWORDS
    ]


def sparse_vector(text: str) -> dict[str, float]:
    """Log-TF sparse lexical vector ``{token: 1 + ln(tf)}`` (§4.4).

    ``tf`` is the raw count of a token in ``text``; the ``1 + ln(tf)`` weight
    saturates repeats so a term seen ten times does not swamp one seen once.
    Returns an empty dict for text made only of stopwords or short fragments
    (e.g. ``"the and для"`` → ``{}``). Deterministic: keys follow first-seen
    order.
    """
    counts: dict[str, int] = {}
    for tok in fold_tokens(text):
        counts[tok] = counts.get(tok, 0) + 1
    return {tok: 1.0 + math.log(tf) for tok, tf in counts.items()}


def sparse_dot(a: dict[str, float], b: dict[str, float]) -> float:
    """Dot product ``Σ a[t]·b[t]`` over tokens shared by both vectors (§4.4).

    Disjoint vectors (no shared token) give ``0.0``; identical non-empty vectors
    give ``Σ w²`` > 0. Iterates the smaller vector for a stable, cheap loop.
    """
    if len(a) > len(b):
        a, b = b, a
    return sum(weight * b[tok] for tok, weight in a.items() if tok in b)


class SparseIndex:
    """Inverted-index sparse retriever with corpus-learned IDF (§4.4).

    :meth:`add` accumulates a log-TF :func:`sparse_vector` per document and an
    inverted index ``token -> [doc positions]`` plus a document-frequency (df)
    table. :meth:`search` scores candidates by
    ``Σ_{t ∈ q∩doc} q[t]·doc[t]·idf(t)`` — a TF·IDF overlap — so a term shared by
    every document (``idf == 0``) contributes nothing. All weights are
    non-negative, hits with a non-positive score are dropped, and ranking ties
    break on ``doc_id`` for determinism.
    """

    def __init__(self) -> None:
        self._doc_ids: list[str] = []
        self._vectors: list[dict[str, float]] = []
        self._postings: dict[str, list[int]] = {}
        self._df: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self._doc_ids)

    def add(self, doc_id: str, text: str) -> None:
        """Index ``text`` under ``doc_id`` (§4.4).

        Builds the document's log-TF vector, appends its posting to every token's
        list and bumps the per-token document frequency. Re-adding a ``doc_id``
        stores a second, independent document (no de-duplication).
        """
        vec = sparse_vector(text)
        pos = len(self._doc_ids)
        self._doc_ids.append(doc_id)
        self._vectors.append(vec)
        for tok in vec:
            self._postings.setdefault(tok, []).append(pos)
            self._df[tok] = self._df.get(tok, 0) + 1

    def idf(self, token: str) -> float:
        """Smoothed IDF ``ln((N + 1) / (df + 1))`` for ``token`` (§4.4).

        ``N`` is the corpus size. Always ``>= 0``; a token present in *every*
        document (``df == N``) yields exactly ``0.0`` (fully down-weighted), while
        a rare token approaches ``ln((N + 1) / 2)``. Unknown/empty corpus → the
        neutral fallback so unseen tokens never dominate.
        """
        n = len(self._doc_ids)
        if n == 0:
            return 0.0
        df = self._df.get(token, 0)
        return math.log((n + 1) / (df + 1))

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """Rank documents against ``query`` by TF·IDF overlap (§4.4).

        Returns up to ``limit`` ``(doc_id, score)`` pairs, most-relevant first,
        with score ties broken by ``doc_id`` (deterministic). An empty index or a
        query whose tokens match no document returns ``[]``.
        """
        if not self._doc_ids:
            return []
        q_vec = sparse_vector(query)
        scores: dict[int, float] = {}
        for tok, q_weight in q_vec.items():
            postings = self._postings.get(tok)
            if not postings:
                continue
            factor = q_weight * self.idf(tok)
            if factor == 0.0:
                continue
            for pos in postings:
                scores[pos] = scores.get(pos, 0.0) + factor * self._vectors[pos][tok]
        ranked = sorted(
            ((self._doc_ids[pos], score) for pos, score in scores.items() if score > 0.0),
            key=lambda hit: (-hit[1], hit[0]),
        )
        return ranked[:limit]
