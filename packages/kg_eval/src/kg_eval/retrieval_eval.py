"""Runnable retrieval eval over the seed graph (§4.11 / §18.6).

A tiny, dependency-light harness that ranks entities of a
:class:`~kg_retrievers.graph_store.KuzuGraphStore` by keyword overlap and scores
the ranking against a hand-curated GOLDEN set of ``(query, relevant_ids)`` pairs
(§15.2: ``Recall@10`` / ``MRR`` для релевантных сущностей seed-графа). The ranking
metrics themselves are reused verbatim from :mod:`kg_eval.retrieval_metrics` — this
module only supplies the *retriever* (keyword-overlap over ``name``/``aliases``/
``text``) and the golden reference, then folds per-query
:class:`~kg_eval.retrieval_metrics.RetrievalMetrics` into a macro-averaged report.

The retriever queries Kuzu directly with parameterized Cypher (an OR of
``CONTAINS`` предфильтров over the indexed text columns), then re-scores the
candidates in Python by exact token overlap so declension noise ("осмос" vs
"осмоса") never inflates a hit. Deterministic: same store + golden → same numbers.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kg_eval.retrieval_metrics import (
    DEFAULT_K,
    RetrievalMetrics,
    aggregate,
    evaluate,
)

if TYPE_CHECKING:  # avoid a hard runtime import cycle; the store is passed in
    from kg_retrievers.graph_store import KuzuGraphStore

# Golden queries reference real seed ids built by kg_retrievers.seed.build_seed_graph
# (ids are the make_id(<label>, <key>) slugs — e.g. tech:reverse-osmosis-desalination).
# Each query's top keyword-overlap hit is the sole relevant id, except the
# multi-relevant "flash smelting" (ПВП) case which exercises Recall@10 / MRR>1-hit.
GOLDEN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ion exchange", ("tech:ion-exchange-desalination",)),
    ("reverse osmosis", ("tech:reverse-osmosis-desalination",)),
    ("wet scrubber", ("tech:wet-scrubber-so2",)),
    ("electrodialysis", ("tech:electrodialysis-desalination",)),
    ("catholyte circulation", ("tech:catholyte-circulation-scheme",)),
    (
        "flash smelting",
        ("regime:flash-smelting-copper", "tech:flash-smelting-furnace-scheme"),
    ),
)

# Text columns scored for keyword overlap (name / канонич. имя / синонимы / текст).
_TEXT_FIELDS: tuple[str, ...] = ("name", "canonical_name", "aliases_text", "text")
_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def _tokenize(text: str | None) -> set[str]:
    """Lowercase alnum/cyrillic tokens (RU/EN) of ``text``; empty for ``None``."""
    return {t.lower() for t in _TOKEN.findall(text or "")}


def _keyword_score(node: dict[str, Any], tokens: set[str]) -> float:
    """Fraction of query ``tokens`` present in the node's text fields (§18.6).

    Mirrors the api-gateway keyword ranker: exact token overlap over
    ``name``/``canonical_name``/``aliases_text``/``text``, normalised by the query
    length so scores land in ``[0, 1]``.
    """
    hay = _tokenize(" ".join(str(node.get(f) or "") for f in _TEXT_FIELDS))
    return len(tokens & hay) / (len(tokens) or 1)


def _candidate_rows(store: KuzuGraphStore, tokens: set[str], limit: int) -> list[list[Any]]:
    """Fetch nodes whose text columns CONTAIN any query token (parameterized)."""
    conds: list[str] = []
    params: dict[str, Any] = {}
    for i, tok in enumerate(sorted(tokens)):
        key = f"t{i}"
        params[key] = tok
        conds.append(
            f"(lower(coalesce(n.name,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.canonical_name,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.aliases_text,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.text,'')) CONTAINS ${key})"
        )
    cypher = "MATCH (n:Node) WHERE " + " OR ".join(conds) + f" RETURN n LIMIT {int(limit)}"
    return store.rows(cypher, params)


def rank_entities(store: KuzuGraphStore, query: str, *, limit: int = 200) -> list[str]:
    """Rank seed entities for ``query`` by keyword overlap, best-first (§18.6).

    Zero-overlap candidates are dropped; ties break by ``id`` for a deterministic
    order. Returns node ids only (the ranked list fed to the ranking metrics).
    """
    tokens = _tokenize(query)
    if not tokens:
        return []
    scored: list[tuple[float, str]] = []
    for row in _candidate_rows(store, tokens, limit):
        node = store._node_dict(row[0])
        nid = node.get("id")
        if not nid:
            continue
        score = _keyword_score(node, tokens)
        if score > 0:
            scored.append((score, nid))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [nid for _, nid in scored]


@dataclass(frozen=True)
class QueryResult:
    """Per-query ranking + its metrics at cutoff ``k`` (§18.6)."""

    query: str
    relevant_ids: tuple[str, ...]
    ranked_ids: tuple[str, ...]
    metrics: RetrievalMetrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "relevant_ids": list(self.relevant_ids),
            "ranked_ids": list(self.ranked_ids),
            "metrics": self.metrics.as_dict(),
        }


@dataclass(frozen=True)
class RetrievalEvalReport:
    """Macro-averaged retrieval eval over the golden set (§4.11 / §15.2)."""

    k: int
    per_query: tuple[QueryResult, ...]
    aggregate: RetrievalMetrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "k": self.k,
            "per_query": [q.as_dict() for q in self.per_query],
            "aggregate": self.aggregate.as_dict(),
        }


def run_retrieval_eval(
    store: KuzuGraphStore,
    golden: Iterable[tuple[str, Sequence[str]]] | None = None,
    *,
    k: int = DEFAULT_K,
    candidate_limit: int = 200,
) -> RetrievalEvalReport:
    """Rank + score every golden query over ``store`` (§4.11 Recall@10/MRR, §18.6).

    ``golden`` defaults to the module :data:`GOLDEN`. For each query the keyword
    ranker produces a ranked id list, scored against its relevant ids into a
    :class:`RetrievalMetrics`; the corpus aggregate is the macro-average computed
    by :func:`kg_eval.retrieval_metrics.aggregate`. An empty golden yields an empty
    ``per_query`` and all-zero aggregate metrics.
    """
    pairs = list(GOLDEN if golden is None else golden)
    per_query: list[QueryResult] = []
    runs: list[tuple[list[str], tuple[str, ...]]] = []
    for query, relevant in pairs:
        rel = tuple(relevant)
        ranked = rank_entities(store, query, limit=candidate_limit)
        per_query.append(
            QueryResult(
                query=query,
                relevant_ids=rel,
                ranked_ids=tuple(ranked),
                metrics=evaluate(ranked, rel, k),
            )
        )
        runs.append((ranked, rel))
    return RetrievalEvalReport(
        k=k,
        per_query=tuple(per_query),
        aggregate=aggregate(runs, k),
    )
