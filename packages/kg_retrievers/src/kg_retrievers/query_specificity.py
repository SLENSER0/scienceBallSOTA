"""Pre-retrieval query-specificity predictors for hybrid search (§12.3, Mode B).

§12.3 (Mode B — hybrid semantic search / гибридный семантический поиск) benefits
from knowing *before* retrieval whether a query is discriminating (specific) or
vague. Where :mod:`kg_retrievers.query_term_weighting` builds a per-term *weight
vector* for assembling the keyword query, this module rolls those term rarities
up into **query-level performance predictors** — scalar scores that summarise how
specific the whole query is.

The rarity of a term is its inverse document frequency (обратная документная
частота), here the plain base-2 form

    idf(t) = log2(N / df(t))

with ``N`` the corpus size and ``df(t)`` the number of documents containing the
term. A term **absent** from the df map (or with ``df < 1``) is treated as
``df = 1`` — a maximally rare, seen-once term — so it never produces a division by
zero and always earns the largest weight ``log2(N)``.

:func:`predict_specificity` folds the query terms (reusing the RU/EN
:func:`kg_common.canonical_key` fold used across the retriever stack), collapses
duplicates, and reports:

* ``avg_idf`` — mean term idf (общая специфичность запроса);
* ``max_idf`` — the single rarest term's idf;
* ``scs``     — the Simplified Clarity Score ``-log2(n_terms) + avg_idf``, which
  discounts the raw specificity by how many distinct terms the query spreads over;
* ``n_terms`` — the number of distinct folded terms.

An empty query yields an all-zero :class:`SpecificityScores`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from kg_common import canonical_key


def _term_idf(term: str, df_map: Mapping[str, int], n_docs: int) -> float:
    """Base-2 idf ``log2(N / df)`` for a folded ``term`` (§12.3).

    A term missing from ``df_map`` — or mapped to ``df < 1`` — is treated as
    ``df = 1`` (an unseen / seen-once, maximally rare term), giving ``log2(N)``.
    """
    df = df_map.get(term, 1)
    if df < 1:
        df = 1
    return math.log2(n_docs / df)


@dataclass(frozen=True, slots=True)
class SpecificityScores:
    """Query-level pre-retrieval specificity predictors (§12.3, Mode B).

    Все поля — скалярные предикторы качества запроса до извлечения.

    * ``avg_idf`` — mean idf over distinct terms (средняя специфичность);
    * ``max_idf`` — idf of the rarest term (максимальная специфичность);
    * ``scs``     — Simplified Clarity Score ``-log2(n_terms) + avg_idf``;
    * ``n_terms`` — count of distinct folded terms.
    """

    avg_idf: float
    max_idf: float
    scs: float
    n_terms: int

    def as_dict(self) -> dict[str, float | int]:
        """Expose ``{avg_idf, max_idf, scs, n_terms}`` for JSON/telemetry."""
        return {
            "avg_idf": self.avg_idf,
            "max_idf": self.max_idf,
            "scs": self.scs,
            "n_terms": self.n_terms,
        }


def predict_specificity(
    terms: list[str],
    df_map: Mapping[str, int],
    n_docs: int,
) -> SpecificityScores:
    """Predict query specificity from corpus document frequencies (§12.3).

    Folds each of ``terms`` with :func:`kg_common.canonical_key`, drops blanks,
    and collapses duplicates so ``n_terms`` counts *distinct* folded terms. Each
    surviving term contributes ``idf(t) = log2(N / df(t))``; a term absent from
    ``df_map`` (or with ``df < 1``) defaults to ``df = 1`` (maximally rare).

    Returns ``avg_idf`` (mean idf), ``max_idf`` (rarest term), and the Simplified
    Clarity Score ``scs = -log2(n_terms) + avg_idf``. An empty query — or one that
    folds away to nothing — yields all-zero scores.
    """
    if n_docs < 1:
        raise ValueError("n_docs must be >= 1")

    distinct: list[str] = []
    seen: set[str] = set()
    for raw in terms:
        folded = canonical_key(raw)
        if not folded or folded in seen:
            continue
        seen.add(folded)
        distinct.append(folded)

    n_terms = len(distinct)
    if n_terms == 0:
        return SpecificityScores(avg_idf=0.0, max_idf=0.0, scs=0.0, n_terms=0)

    idfs = [_term_idf(term, df_map, n_docs) for term in distinct]
    avg_idf = sum(idfs) / n_terms
    max_idf = max(idfs)
    scs = -math.log2(n_terms) + avg_idf
    return SpecificityScores(
        avg_idf=avg_idf,
        max_idf=max_idf,
        scs=scs,
        n_terms=n_terms,
    )
