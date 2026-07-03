"""Field-weighted BM25F scoring for hybrid semantic search (§12.3, Mode B).

§12.3 (Mode B — hybrid semantic search / гибридный семантический поиск) ranks
documents with a keyword channel alongside the dense one. Where
:mod:`kg_retrievers.sparse` emits *unweighted* log-TF token vectors and
:mod:`kg_retrievers.query_term_weighting` turns a query into an **IDF-only**
weighted vector, neither applies a *field-boosted* BM25F. This module fills that
gap: it scores a single document whose text is split across named fields
(``title`` / ``body`` / ``table_caption`` …), each with its own boost, length
normalisation and average length.

BM25F (см. Robertson & Zaragoza) differs from plain BM25 by combining the
per-field term frequencies **before** the ``k1`` saturation, not after. For a
term ``t`` the field-weighted frequency (взвешенная частота) is

    tf̃_t = Σ_f  boost_f · tf_{t,f} / (1 − b_f + b_f · len_f / avglen_f)

(the divisor is the per-field length normalisation: a field longer than its
average ``avglen`` is discounted when ``b_f > 0``, and with ``b_f = 0`` the
divisor is exactly ``1``). The term then saturates *once*, jointly:

    score_t = idf(t) · tf̃_t / (k1 + tf̃_t)

so two fields carrying the same term reinforce each other before saturation
rather than each saturating on its own. The document score is ``Σ_t score_t``.

A term absent from every field has ``tf̃ = 0`` → ``score_t = 0``. A term with
``idf = 0`` (present in every corpus document) contributes ``0`` regardless of
frequency. The result is a frozen :class:`BM25FScore` (``doc_id`` / ``score`` /
``per_term``) with :meth:`~BM25FScore.as_dict`.
"""

from __future__ import annotations

from dataclasses import dataclass

# field_cfg value = (boost, b, avglen): field boost, length-normalisation b in
# [0, 1], and the corpus average length of that field (§12.3).
FieldCfg = dict[str, tuple[float, float, float]]


@dataclass(frozen=True)
class BM25FScore:
    """A document's BM25F score with its per-term breakdown (§12.3, Mode B).

    ``doc_id`` identifies the scored document; ``score`` is the total
    ``Σ per_term`` value; ``per_term`` maps each query term to its (non-negative)
    contribution, including ``0.0`` for terms absent from the document or with
    ``idf == 0``. Deterministic: ``per_term`` keys follow first-seen query order.
    """

    doc_id: str
    score: float
    per_term: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "score": self.score,
            "per_term": dict(self.per_term),
        }


def _weighted_tf(
    term: str,
    field_tf: dict[str, dict[str, int]],
    field_len: dict[str, int],
    field_cfg: FieldCfg,
) -> float:
    """Field-weighted frequency ``tf̃_t = Σ_f boost·tf/(1−b+b·len/avglen)`` (§12.3).

    Iterates the configured fields; a field where ``term`` has zero frequency
    contributes nothing, so its length is irrelevant. A field whose length is
    missing from ``field_len`` falls back to its own ``avglen`` (neutral divisor
    ``1``). The per-field contributions sum **before** the ``k1`` saturation.
    """
    total = 0.0
    for field, (boost, b, avglen) in field_cfg.items():
        tf = field_tf.get(field, {}).get(term, 0)
        if tf == 0:
            continue
        flen = field_len.get(field, avglen)
        denom = 1.0 - b + b * flen / avglen
        total += boost * tf / denom
    return total


def score_bm25f(
    doc_id: str,
    query_terms: list[str],
    field_tf: dict[str, dict[str, int]],
    field_len: dict[str, int],
    field_cfg: FieldCfg,
    idf_map: dict[str, float],
    k1: float = 1.2,
) -> BM25FScore:
    """Score ``doc_id`` against ``query_terms`` with field-weighted BM25F (§12.3).

    For each unique query term the field-weighted frequency ``tf̃`` is built by
    :func:`_weighted_tf` (per-field boost + length normalisation, combined before
    saturation), then the term contributes ``idf · tf̃ / (k1 + tf̃)`` where ``idf``
    comes from ``idf_map`` (missing term → ``0.0``). A term absent from the
    document (``tf̃ = 0``) or with ``idf = 0`` contributes exactly ``0.0``. The
    total ``score`` is the sum of ``per_term`` values; ``per_term`` retains every
    query term in first-seen order (duplicates collapse to one key).
    """
    per_term: dict[str, float] = {}
    for term in query_terms:
        if term in per_term:
            continue
        tf_tilde = _weighted_tf(term, field_tf, field_len, field_cfg)
        idf = idf_map.get(term, 0.0)
        if tf_tilde <= 0.0 or idf == 0.0:
            per_term[term] = 0.0
            continue
        per_term[term] = idf * tf_tilde / (k1 + tf_tilde)
    return BM25FScore(doc_id=doc_id, score=sum(per_term.values()), per_term=per_term)
