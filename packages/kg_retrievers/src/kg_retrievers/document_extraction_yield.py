"""Per-document MENTIONS→observation extraction yield (§25.7).

Выход извлечения по документу — for each source document, measures how many of the
entity/property *mentions* were successfully backed by an *observation* in the graph.
A mention is a ``(entity_id, property_name)`` pair asserted for a document; it is
*observed* when a corresponding measurement/observation exists. The per-document
``yield_ratio`` is ``observed / mentioned``; the overall yield aggregates across all
documents. Mentions lacking an observation are collected as ``missed`` pairs so callers
can drive re-extraction.

Pure in-memory computation over plain ``dict`` records — no graph access. Результат —
frozen dataclasses with ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocYield:
    """Extraction yield for one document (§25.7).

    ``mentioned`` mentions were asserted for ``doc_id``; ``observed`` of them are backed
    by an observation. ``missed`` lists the ``(entity_id, property_name)`` pairs that
    lacked an observation. ``yield_ratio == observed / mentioned``.
    """

    doc_id: str
    mentioned: int
    observed: int
    yield_ratio: float
    missed: list[tuple[str, str]]

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "mentioned": self.mentioned,
            "observed": self.observed,
            "yield_ratio": self.yield_ratio,
            "missed": [list(pair) for pair in self.missed],
        }


@dataclass(frozen=True)
class YieldSummary:
    """Aggregate extraction-yield report across documents (§25.7).

    ``overall_yield`` is total observed over total mentioned across all docs (``0.0`` when
    nothing was mentioned). ``worst_docs`` holds the ``doc_id``s with the lowest yield,
    ascending, truncated to ``worst_n``.
    """

    docs: list[DocYield]
    overall_yield: float
    worst_docs: list[str]

    def as_dict(self) -> dict:
        return {
            "docs": [d.as_dict() for d in self.docs],
            "overall_yield": self.overall_yield,
            "worst_docs": list(self.worst_docs),
        }


def document_extraction_yield(
    records: list[dict],
    *,
    worst_n: int = 3,
) -> YieldSummary:
    """Compute per-document MENTIONS→observation extraction yield (§25.7).

    Выход извлечения по документу. Each record is
    ``{doc_id, entity_id, property_name, has_observation}``. For every document with at
    least one mention, computes ``yield_ratio = observed / mentioned`` and collects the
    ``(entity_id, property_name)`` pairs whose ``has_observation`` is false into
    ``missed``. Documents with zero mentions are skipped. ``worst_docs`` ranks the docs
    ascending by ``yield_ratio`` (ties broken by ``doc_id``) and is truncated to
    ``worst_n``.
    """
    per_doc_mentioned: dict[str, int] = {}
    per_doc_observed: dict[str, int] = {}
    per_doc_missed: dict[str, list[tuple[str, str]]] = {}
    order: list[str] = []

    for rec in records:
        doc_id = rec["doc_id"]
        if doc_id not in per_doc_mentioned:
            per_doc_mentioned[doc_id] = 0
            per_doc_observed[doc_id] = 0
            per_doc_missed[doc_id] = []
            order.append(doc_id)
        per_doc_mentioned[doc_id] += 1
        if rec["has_observation"]:
            per_doc_observed[doc_id] += 1
        else:
            per_doc_missed[doc_id].append((rec["entity_id"], rec["property_name"]))

    docs: list[DocYield] = []
    total_mentioned = 0
    total_observed = 0
    for doc_id in order:
        mentioned = per_doc_mentioned[doc_id]
        if mentioned == 0:
            continue
        observed = per_doc_observed[doc_id]
        total_mentioned += mentioned
        total_observed += observed
        docs.append(
            DocYield(
                doc_id=doc_id,
                mentioned=mentioned,
                observed=observed,
                yield_ratio=observed / mentioned,
                missed=per_doc_missed[doc_id],
            )
        )

    overall_yield = total_observed / total_mentioned if total_mentioned else 0.0
    ranked = sorted(docs, key=lambda d: (d.yield_ratio, d.doc_id))
    worst_docs = [d.doc_id for d in ranked[:worst_n]]

    return YieldSummary(docs=docs, overall_yield=overall_yield, worst_docs=worst_docs)
