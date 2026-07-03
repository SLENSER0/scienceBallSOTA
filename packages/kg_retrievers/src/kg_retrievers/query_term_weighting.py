"""IDF/BM25 query-term weighting for hybrid semantic search (§12.3, Mode B).

§12.3 (Mode B — hybrid semantic search / гибридный семантический поиск) builds a
sparse/keyword query alongside the dense one. Where :mod:`kg_retrievers.sparse`
emits *unweighted* log-TF token vectors and :mod:`kg_retrievers.query_expansion`
*broadens* a query with aliases, this module does neither: it turns a raw query
into a **weighted term vector** ``{term: idf-weight}`` using a corpus
document-frequency (df, документная частота) map, so rare, discriminating terms
outweigh common ones when the keyword query is assembled.

The weight is the BM25 inverse-document-frequency (обратная документная частота)

    idf(df, N) = ln(1 + (N - df + 0.5) / (df + 0.5))

which is *strictly positive* for every ``1 <= df <= N`` (the ``+0.5`` smoothing
keeps the argument above ``1``) and rises as ``df`` falls, so a term seen in one
document out of ``N`` is weighted above one seen in nearly all of them.

:func:`build_weighted_query` folds the query to lowercase tokens (reusing the
same RU/EN fold as the rest of the retriever stack via
:func:`kg_common.canonical_key`), collapses duplicates, drops stopwords
(стоп-слова) and terms whose idf falls below ``min_idf``, then maps each surviving
term to its idf weight. A query term **absent** from ``df_map`` is treated as
``df = 0`` — an unseen, maximally rare term — and therefore kept with the highest
weight. The result is a frozen :class:`WeightedQuery` (``terms`` / ``dropped``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from kg_common import canonical_key

# Token = maximal run of RU/EN letters or digits over the canonical-key fold
# (NFKC + lower-case + separator collapse, Cyrillic preserved).
_TOKEN_RE = re.compile(r"[0-9a-zа-яё]+")


def _fold_tokens(text: str) -> list[str]:
    """Lowercase-fold ``text`` to an order-preserving list of tokens (§12.3).

    Reuses :func:`kg_common.canonical_key` for the fold, then keeps maximal runs
    of RU/EN letters or digits. Repeats are preserved here; duplicate collapse
    happens at the term level in :func:`build_weighted_query`.
    """
    return _TOKEN_RE.findall(canonical_key(text))


def bm25_idf(df: int, n_docs: int) -> float:
    """BM25 inverse document frequency ``ln(1 + (N - df + 0.5) / (df + 0.5))`` (§12.3).

    ``df`` is the number of documents containing the term, ``N`` the corpus size.
    Strictly positive for every ``0 <= df <= N`` (the ``+0.5`` smoothing keeps the
    logarithm's argument above ``1``); monotonically **decreasing** in ``df``, so a
    rarer term (small ``df``) is weighted above a common one. ``df = 0`` (unseen
    term) yields the largest weight.
    """
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


@dataclass(frozen=True)
class WeightedQuery:
    """A query folded to an idf-weighted term vector (§12.3, Mode B).

    ``terms`` maps each surviving lowercase term to its BM25 idf weight (strictly
    positive); ``dropped`` holds the terms filtered out as stopwords or for
    ``idf < min_idf``, in first-seen order. Deterministic: ``terms`` keys follow
    first-seen token order.
    """

    terms: dict[str, float]
    dropped: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "terms": dict(self.terms),
            "dropped": list(self.dropped),
        }


def build_weighted_query(
    query: str,
    df_map: Mapping[str, int],
    n_docs: int,
    *,
    stopwords: frozenset[str] = frozenset(),
    min_idf: float = 0.0,
) -> WeightedQuery:
    """Turn ``query`` into an idf-weighted term vector over ``df_map`` (§12.3).

    Folds ``query`` to lowercase tokens (:func:`_fold_tokens`), collapses
    duplicates (so ``"Steel steel"`` yields a single ``steel``), and for each
    unique term looks up its document frequency in ``df_map`` — a term absent from
    ``df_map`` is treated as ``df = 0`` (unseen → highest weight, retained). A term
    in ``stopwords`` is dropped; so is one whose :func:`bm25_idf` weight is below
    ``min_idf``. Surviving terms map to their idf weight (always ``> 0``).
    """
    terms: dict[str, float] = {}
    dropped: list[str] = []
    seen: set[str] = set()
    for term in _fold_tokens(query):
        if term in seen:
            continue
        seen.add(term)
        if term in stopwords:
            dropped.append(term)
            continue
        df = df_map.get(term, 0)
        weight = bm25_idf(df, n_docs)
        if weight < min_idf:
            dropped.append(term)
            continue
        terms[term] = weight
    return WeightedQuery(terms=terms, dropped=tuple(dropped))
