"""PaperQA2 / ContraCrow cross-source contradiction detection (§15.4 / §13).

Кросс-документное выявление противоречий — pure-python detector inspired by the
**ContraCrow** contradiction-mining agent of *PaperQA2* (Skarlinski et al.,
"Language agents achieve superhuman synthesis of scientific knowledge",
FutureHouse, arXiv:2409.13740). PaperQA2 scans a corpus for *cross-source*
disagreements and reports on the order of **~2.34 contradictions per paper**;
this module reproduces the core cross-document self-consistency check as a
transparent heuristic, without an LLM in the loop.

Given a list of atomic *claim* dicts ``{id, subject, property, value?,
polarity?, doc_id}``, :func:`detect_contradictions` groups claims by their
``(subject, property)`` topic and flags any two claims **from different
documents** that disagree, either

- ``numeric`` — both carry a numeric ``value`` and the relative divergence
  ``|a-b| / max(|a|, |b|)`` reaches ``DIVERGENCE_THRESHOLD`` (0.30), or
- ``polarity`` — their qualitative ``polarity`` points opposite ways (one
  supports / positive, the other refutes / negative).

Two claims from the *same* document never contradict each other — intra-document
self-consistency (внутридокументная самосогласованность) is assumed, mirroring
PaperQA2's cross-source framing. :func:`contradiction_rate` returns the PaperQA2
metric — contradiction pairs divided by the number of distinct documents.

The module is pure and side-effect free — it never touches the graph store.
Results are frozen dataclasses exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ContradictionPair",
    "detect_contradictions",
    "contradiction_rate",
    "DIVERGENCE_THRESHOLD",
]

# A single atomic claim dict; reconciliation keys are read defensively.
Claim = dict[str, Any]

# §15.4 relative-divergence threshold (mirrors the rest of the retriever stack).
DIVERGENCE_THRESHOLD = 0.30

# Polarity synonyms → canonical {'positive', 'negative'} (§13). A claim opposes
# another only when one side is positive and the other negative.
_POSITIVE = frozenset(
    {"positive", "support", "supports", "supported", "confirm", "confirmed", "yes", "true", "+"}
)
_NEGATIVE = frozenset(
    {"negative", "refute", "refutes", "refuted", "contradict", "disproven", "no", "false", "-"}
)


@dataclass(frozen=True)
class ContradictionPair:
    """One cross-document contradiction between two claims (§15.4 / §13).

    Пара противоречащих утверждений. ``claim_a`` / ``claim_b`` are the two claim
    ids; ``subject`` is the shared topic subject; ``kind`` is ``'numeric'`` (point
    values diverge by ``>= DIVERGENCE_THRESHOLD``) or ``'polarity'`` (opposite
    qualitative stance). ``divergence`` is the relative numeric divergence for a
    ``numeric`` pair, or ``1.0`` for a fully-opposed ``polarity`` pair.
    ``doc_ids`` are the two distinct source documents, in ``(a, b)`` order.
    """

    claim_a: str
    claim_b: str
    subject: str
    kind: str
    divergence: float
    doc_ids: tuple[str, str]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of all six fields (§15.4)."""
        return {
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "subject": self.subject,
            "kind": self.kind,
            "divergence": self.divergence,
            "doc_ids": list(self.doc_ids),
        }


def _as_float(value: Any) -> float | None:
    """Best-effort float coercion; ``None`` on missing/bool/malformed input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _canonical_polarity(value: Any) -> str | None:
    """Map a polarity token to ``'positive'`` / ``'negative'`` (else ``None``)."""
    if isinstance(value, bool):
        return "positive" if value else "negative"
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    if key in _POSITIVE:
        return "positive"
    if key in _NEGATIVE:
        return "negative"
    return None


def _classify_pair(a: Claim, b: Claim, subject: str) -> ContradictionPair | None:
    """Decide whether two different-doc claims contradict (numeric | polarity).

    Numeric divergence takes precedence: if both claims carry a numeric ``value``
    and their relative divergence reaches the threshold, a ``numeric`` pair is
    returned. Otherwise an opposing ``polarity`` yields a ``polarity`` pair. When
    neither fires the claims agree (or are unconstrained) and ``None`` is
    returned.
    """
    doc_ids = (str(a.get("doc_id")), str(b.get("doc_id")))

    va, vb = _as_float(a.get("value")), _as_float(b.get("value"))
    if va is not None and vb is not None:
        scale = max(abs(va), abs(vb))
        if scale > 0.0:
            rel = abs(va - vb) / scale
            if rel >= DIVERGENCE_THRESHOLD:
                return ContradictionPair(
                    claim_a=str(a.get("id")),
                    claim_b=str(b.get("id")),
                    subject=subject,
                    kind="numeric",
                    divergence=round(rel, 4),
                    doc_ids=doc_ids,
                )

    pa, pb = _canonical_polarity(a.get("polarity")), _canonical_polarity(b.get("polarity"))
    if pa is not None and pb is not None and {pa, pb} == {"positive", "negative"}:
        return ContradictionPair(
            claim_a=str(a.get("id")),
            claim_b=str(b.get("id")),
            subject=subject,
            kind="polarity",
            divergence=1.0,
            doc_ids=doc_ids,
        )

    return None


def detect_contradictions(claims: list[Claim]) -> list[ContradictionPair]:
    """Detect cross-document contradictions across a claim set (§15.4 / §13).

    Выявление противоречий. Claims are grouped by their ``(subject, property)``
    topic; within each group every unordered pair drawn from **different**
    documents is tested by :func:`_classify_pair`. Pairs are emitted in a
    deterministic order — groups sorted by ``(subject, property)`` string key,
    then by the claims' input order within a group. Same-document pairs are
    skipped (self-consistency), so a single noisy document cannot contradict
    itself.
    """
    groups: dict[tuple[Any, Any], list[Claim]] = defaultdict(list)
    for claim in claims:
        groups[(claim.get("subject"), claim.get("property"))].append(claim)

    pairs: list[ContradictionPair] = []
    for (subject, _prop), members in sorted(
        groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if a.get("doc_id") == b.get("doc_id"):
                    continue  # intra-document → self-consistent, never flagged
                pair = _classify_pair(a, b, str(subject))
                if pair is not None:
                    pairs.append(pair)
    return pairs


def contradiction_rate(claims: list[Claim]) -> float:
    """Contradiction pairs per document — the PaperQA2 metric (~2.34/paper).

    Плотность противоречий. Returns ``len(detect_contradictions(claims)) /
    n_docs`` where ``n_docs`` is the number of distinct non-null ``doc_id``
    values. An empty corpus (no documents) yields ``0.0``.
    """
    docs = {c.get("doc_id") for c in claims if c.get("doc_id") is not None}
    if not docs:
        return 0.0
    return len(detect_contradictions(claims)) / len(docs)
