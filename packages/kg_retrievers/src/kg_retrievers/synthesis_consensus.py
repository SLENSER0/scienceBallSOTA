"""Synthesis-level consensus vs disagreement aggregator (§24.11).

Аналитика/синтез — agreement across *independent* sources. Where the pairwise
``contradiction_detector`` compares two measurements at a time, this module works
at the **synthesis** level: it collapses every claim about one ``property_id``
into a single :class:`ClaimGroup` and labels it as

- ``consensus`` — confirmed by ``>= min_sources`` *distinct* sources whose values
  agree within ``rel_tol`` (подтверждено независимыми источниками);
- ``disagreement`` — several distinct sources but their values spread wider than
  ``rel_tol`` (расхождение между источниками);
- ``single`` — only one distinct source contributes (единственный источник).

Independence is measured by *distinct* ``source_id``: duplicate claims from the
same source count once toward ``n_independent`` (self-citation does not create
consensus). The module is pure and side-effect free — it never touches the graph
store; results are frozen dataclasses exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["ClaimGroup", "is_consensus", "group_claims"]

# A single claim: {"property_id": str, "value": float, "source_id": str}.
Claim = dict[str, Any]


@dataclass(frozen=True)
class ClaimGroup:
    """Aggregated verdict over all claims about one property (§24.11)."""

    property_id: str
    verdict: str  # {'consensus', 'disagreement', 'single'}
    source_ids: tuple[str, ...]
    n_independent: int
    value_min: float | None
    value_max: float | None

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly projection (§24.11)."""
        return {
            "property_id": self.property_id,
            "verdict": self.verdict,
            "source_ids": list(self.source_ids),
            "n_independent": self.n_independent,
            "value_min": self.value_min,
            "value_max": self.value_max,
        }


def is_consensus(
    values: list[float],
    sources: list[str],
    *,
    rel_tol: float = 0.05,
    min_sources: int = 2,
) -> bool:
    """True iff ``>= min_sources`` distinct sources agree within ``rel_tol``.

    Consensus requires enough *independent* sources (по различным ``source_id``)
    and a tight value spread: ``(max - min) / max <= rel_tol`` (§24.11).
    """
    if not values or not sources:
        return False
    n_independent = len(set(sources))
    if n_independent < min_sources:
        return False
    hi = max(values)
    lo = min(values)
    if hi <= 0:
        # Non-positive scale: fall back to exact agreement (avoid div-by-zero).
        return hi == lo
    return (hi - lo) / hi <= rel_tol


def group_claims(claims: list[Claim], *, rel_tol: float = 0.05) -> list[ClaimGroup]:
    """Group claims by ``property_id`` and label consensus vs disagreement (§24.11).

    Each claim is ``{"property_id", "value", "source_id"}``. Groups preserve
    first-seen property order; ``source_ids`` are the distinct sources in
    first-seen order (независимые источники).
    """
    order: list[str] = []
    buckets: dict[str, list[Claim]] = {}
    for claim in claims:
        pid = claim["property_id"]
        if pid not in buckets:
            buckets[pid] = []
            order.append(pid)
        buckets[pid].append(claim)

    groups: list[ClaimGroup] = []
    for pid in order:
        rows = buckets[pid]
        values = [float(r["value"]) for r in rows]
        # Distinct sources in first-seen order (independence dedup).
        seen: set[str] = set()
        source_ids: list[str] = []
        for r in rows:
            sid = r["source_id"]
            if sid not in seen:
                seen.add(sid)
                source_ids.append(sid)
        n_independent = len(source_ids)

        if n_independent < 2:
            verdict = "single"
        elif is_consensus(values, source_ids, rel_tol=rel_tol, min_sources=2):
            verdict = "consensus"
        else:
            verdict = "disagreement"

        groups.append(
            ClaimGroup(
                property_id=pid,
                verdict=verdict,
                source_ids=tuple(source_ids),
                n_independent=n_independent,
                value_min=min(values) if values else None,
                value_max=max(values) if values else None,
            )
        )
    return groups
