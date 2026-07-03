"""GraphRAG Mode C evaluation metrics (§11.13).

Mode C is the community-summary answering path: the model produces a set of
*claims*, each optionally citing source documents and each flagged as supported
or not.  This module scores four properties of such a claim batch — RU/EN:

* ``citation_precision`` — доля claims с непустыми cited_doc_ids /
  fraction of claims that cite at least one document.
* ``unsupported_claim_rate`` — доля неподтверждённых claims /
  fraction of claims flagged ``supported=False``.
* ``community_coverage`` — доля покрытых communities /
  fraction of the corpus communities actually used to answer.
* ``numeric_accuracy`` — доля верных числовых claims /
  fraction of numeric claims whose value checked out.

All returned ratios lie in ``[0, 1]``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeCMetrics:
    """Frozen bundle of Mode C answer-quality ratios (§11.13)."""

    citation_precision: float
    unsupported_claim_rate: float
    community_coverage: float
    numeric_accuracy: float

    def as_dict(self) -> dict[str, float]:
        """Return the four ratios as plain floats (RU: как словарь float)."""
        return {
            "citation_precision": float(self.citation_precision),
            "unsupported_claim_rate": float(self.unsupported_claim_rate),
            "community_coverage": float(self.community_coverage),
            "numeric_accuracy": float(self.numeric_accuracy),
        }


def evaluate_mode_c(
    claims: list[dict],
    *,
    used_community_ids: list[str],
    total_communities: int,
) -> ModeCMetrics:
    """Score a Mode C claim batch against citation/support/coverage/numeric checks.

    Каждый claim / each ``claim`` dict has keys:
      * ``text`` — the claim string.
      * ``cited_doc_ids`` — list of cited document ids (may be empty).
      * ``supported`` — bool, whether the claim is grounded.
      * ``numeric_ok`` — ``bool`` if the claim carries a number, else ``None``.
    """
    n = len(claims)
    if n:
        cited = sum(1 for c in claims if c.get("cited_doc_ids"))
        unsupported = sum(1 for c in claims if c.get("supported") is False)
        citation_precision = cited / n
        unsupported_claim_rate = unsupported / n
    else:
        citation_precision = 0.0
        unsupported_claim_rate = 0.0

    if total_communities > 0:
        community_coverage = len(set(used_community_ids)) / total_communities
    else:
        community_coverage = 0.0

    numeric = [c for c in claims if c.get("numeric_ok") is not None]
    numeric_accuracy = sum(1 for c in numeric if c["numeric_ok"]) / len(numeric) if numeric else 1.0

    return ModeCMetrics(
        citation_precision=citation_precision,
        unsupported_claim_rate=unsupported_claim_rate,
        community_coverage=community_coverage,
        numeric_accuracy=numeric_accuracy,
    )
