"""Answer-tier classification for synthesis statements (§24.11).

Явно разделять уровни ответа: подтверждённые факты, обзорные выводы,
рекомендации и гипотезы — и НЕ включать неподтверждённые утверждения.

Where ``synthesis_consensus`` decides *whether* independent sources agree, this
module answers a distinct question: given a set of already-formed synthesis
statements, into which of the four §24.11 answer tiers does each belong, and
which must be dropped entirely. A statement is placed by its ``'kind'`` field:

- ``confirmed_fact`` — подтверждённый факт (supported by cited evidence);
- ``review_conclusion`` — обзорный вывод (synthesis over the corpus);
- ``recommendation`` — рекомендация (actionable advice);
- ``hypothesis`` — гипотеза (tentative, still evidence-backed).

Any statement with **no** ``evidence_ids`` is *unsupported* and is DROPPED
regardless of its kind — unsupported claims never reach the answer (§24.11).
The module is pure and side-effect free; it never touches the graph store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["TIERS", "TieredStatement", "tier_statements"]

# The four §24.11 answer tiers, in canonical (most→least established) order.
TIERS: tuple[str, ...] = (
    "confirmed_fact",
    "review_conclusion",
    "recommendation",
    "hypothesis",
)

# A raw synthesis statement: {"text": str, "kind": str, "evidence_ids": list[str]}.
Statement = dict[str, Any]


@dataclass(frozen=True)
class TieredStatement:
    """A synthesis statement assigned to one §24.11 answer tier."""

    text: str
    tier: str  # one of TIERS
    evidence_ids: tuple[str, ...]
    n_sources: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly projection (§24.11)."""
        return {
            "text": self.text,
            "tier": self.tier,
            "evidence_ids": list(self.evidence_ids),
            "n_sources": self.n_sources,
        }


def _dedup(evidence_ids: list[str]) -> tuple[str, ...]:
    """Deduplicate evidence ids preserving first-seen order (независимые источники)."""
    seen: set[str] = set()
    out: list[str] = []
    for eid in evidence_ids:
        if eid not in seen:
            seen.add(eid)
            out.append(eid)
    return tuple(out)


def tier_statements(statements: list[Statement]) -> dict[str, tuple[TieredStatement, ...]]:
    """Classify statements into the four §24.11 tiers, dropping unsupported ones.

    Каждое утверждение — ``{"text", "kind", "evidence_ids"}``. Раскладываем по
    полю ``kind`` в один из четырёх уровней ответа. Утверждение без
    ``evidence_ids`` (неподтверждённое) отбрасывается независимо от ``kind`` —
    такие claims не попадают в ответ (§24.11).

    Returns a mapping keyed by **all four** tiers (empty tuples allowed). Within a
    tier, statements keep their input order. ``evidence_ids`` are deduplicated and
    ``n_sources`` equals the deduplicated count. Raises ``ValueError`` on an
    unknown ``kind``.
    """
    buckets: dict[str, list[TieredStatement]] = {tier: [] for tier in TIERS}
    for stmt in statements:
        kind = stmt["kind"]
        if kind not in buckets:
            raise ValueError(f"unknown statement kind: {kind!r}")
        evidence_ids = _dedup(list(stmt.get("evidence_ids") or []))
        if not evidence_ids:
            # Unsupported claim — never reaches the answer (§24.11).
            continue
        buckets[kind].append(
            TieredStatement(
                text=stmt["text"],
                tier=kind,
                evidence_ids=evidence_ids,
                n_sources=len(evidence_ids),
            )
        )
    return {tier: tuple(rows) for tier, rows in buckets.items()}
