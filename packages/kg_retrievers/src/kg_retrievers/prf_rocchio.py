"""Pseudo-relevance-feedback query expansion — Rocchio (§12.3 Mode B, pure python).

§12.3 Mode B (гибридный семантический поиск) complements the alias-only
:mod:`kg_retrievers.query_expansion` with *content*-based расширение запроса: after a first
retrieval pass the top hits are assumed relevant (pseudo-relevance) and their sparse
term-weight vectors are folded back into the query vector via the classic **Rocchio**
update::

    q' = alpha * q + beta * centroid(relevant) - gamma * centroid(nonrelevant)

Vectors are sparse ``dict[str, float]`` maps (term -> weight); a missing dimension counts as
0. Negative weights in ``q'`` are clamped to 0 (a term seen only in non-relevant docs is
*dropped*, never negative), and ``top_terms`` optionally trims to the highest-weight dims.

The result is a frozen :class:`RocchioResult` (``vector`` / ``added_terms`` / the three
coefficients) with an ``as_dict`` projection. Pure python: no store handles, no network.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


def _centroid(vectors: Sequence[dict[str, float]]) -> dict[str, float]:
    """Mean vector over ``vectors`` — центроид; a dim absent from a vector counts as 0.

    Averaging divides by ``len(vectors)`` (the full count), *not* by how many vectors carry
    the dim, so absent dimensions correctly pull the mean toward 0. Empty input -> ``{}``.
    """
    n = len(vectors)
    if n == 0:
        return {}
    acc: dict[str, float] = {}
    for vec in vectors:
        for term, weight in vec.items():
            acc[term] = acc.get(term, 0.0) + weight
    return {term: total / n for term, total in acc.items()}


@dataclass(frozen=True)
class RocchioResult:
    """A Rocchio-expanded query vector plus the terms it newly introduced (§12.3 Mode B).

    ``vector`` is the clamped (and optionally trimmed) ``q'`` term-weight map. ``added_terms``
    are the dims present in ``vector`` that were *absent* from the original query — the
    pseudo-relevance additions, in deterministic order (highest weight first, then term).
    ``alpha`` / ``beta`` / ``gamma`` echo the coefficients used for auditability.
    """

    vector: dict[str, float]
    added_terms: tuple[str, ...]
    alpha: float
    beta: float
    gamma: float

    def as_dict(self) -> dict:
        return {
            "vector": dict(self.vector),
            "added_terms": list(self.added_terms),
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
        }


def rocchio_expand(
    query: dict[str, float],
    relevant: Sequence[dict[str, float]],
    nonrelevant: Sequence[dict[str, float]] = (),
    *,
    alpha: float = 1.0,
    beta: float = 0.75,
    gamma: float = 0.15,
    top_terms: int | None = None,
) -> RocchioResult:
    """Rocchio query-vector expansion over sparse term weights (§12.3 Mode B).

    Computes ``q' = alpha*q + beta*centroid(relevant) - gamma*centroid(nonrelevant)`` across
    the union of all dimensions (missing dims = 0), clamps every negative weight to 0, and —
    when ``top_terms`` is given — keeps only that many highest-weight dims (ties broken by
    term for determinism). ``added_terms`` lists surviving dims not in the original ``query``.
    """
    rel_c = _centroid(relevant)
    nonrel_c = _centroid(nonrelevant)

    dims = set(query) | set(rel_c) | set(nonrel_c)
    updated: dict[str, float] = {}
    for term in dims:
        weight = (
            alpha * query.get(term, 0.0)
            + beta * rel_c.get(term, 0.0)
            - gamma * nonrel_c.get(term, 0.0)
        )
        if weight > 0.0:
            updated[term] = weight

    if top_terms is not None:
        kept = sorted(updated.items(), key=lambda kv: (-kv[1], kv[0]))[: max(top_terms, 0)]
        updated = dict(kept)

    original_terms = set(query)
    added = tuple(
        term
        for term, _ in sorted(updated.items(), key=lambda kv: (-kv[1], kv[0]))
        if term not in original_terms
    )
    return RocchioResult(
        vector=updated,
        added_terms=added,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
    )
