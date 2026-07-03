"""Gap-prioritization dashboard aggregation (§15.6).

The gap scanner (:mod:`kg_retrievers.gap_analysis`, §15) materializes many
``Gap`` nodes, and §15.9 (:mod:`kg_retrievers.gap_scoring`) scores and explains a
single gap. §15.6 rolls those up into one *dashboard* a curator can act on: how
many gaps sit in each domain / type / owner bucket, and which handful matter most
right now.

:func:`build_gap_dashboard` reads every ``:Gap`` node from a
:class:`~kg_retrievers.graph_store.KuzuGraphStore`, reuses
:func:`~kg_retrievers.gap_scoring.gap_priority_score` for a per-gap priority in
``[0, 1]`` and :func:`~kg_retrievers.gap_scoring.gap_explanation` for a short
Russian (RU) *why*, then returns a frozen :class:`GapDashboard` with:

- **by_domain / by_type / by_owner** — сгруппированные счётчики (grouped counts),
  each ordered by descending count then key for a stable, readable view;
- **top_gaps** — the top-N gaps ranked by priority (descending, ties stable),
  each carrying its score and RU explanation;
- **totals** — итоги: gap count plus the number of distinct domains/types/owners.

Kuzu note: custom gap props (owner, absence_confidence, …) are *not* queryable
columns — we ``RETURN`` only the base ``id`` column and read the full node dict
(base columns merged with the JSON ``props`` catch-all) via
:meth:`~kg_retrievers.graph_store.KuzuGraphStore.get_node`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from kg_retrievers.gap_scoring import gap_explanation, gap_priority_score
from kg_retrievers.graph_store import KuzuGraphStore

# RU fallback bucket labels for gaps missing a domain / owner / type (§15.6).
UNKNOWN_DOMAIN = "без домена"
UNKNOWN_OWNER = "без владельца"
UNKNOWN_TYPE = "неизвестный тип"


@dataclass(frozen=True)
class GapDashboard:
    """Aggregated gap-prioritization view over the graph (§15.6).

    ``by_domain`` / ``by_type`` / ``by_owner`` are grouped counts (bucket → n);
    ``top_gaps`` is the priority-ranked shortlist (each a dict with ``score`` and
    RU ``explanation``); ``totals`` holds the gap count and distinct-bucket sizes.
    """

    by_domain: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)
    by_owner: dict[str, int] = field(default_factory=dict)
    top_gaps: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "by_domain": dict(self.by_domain),
            "by_type": dict(self.by_type),
            "by_owner": dict(self.by_owner),
            "top_gaps": [dict(g) for g in self.top_gaps],
            "totals": dict(self.totals),
        }


def _text(value: object, fallback: str) -> str:
    """A trimmed non-empty string, else the RU ``fallback`` bucket label."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _domain_of(gap: dict[str, Any]) -> str:
    return _text(gap.get("domain"), UNKNOWN_DOMAIN)


def _type_of(gap: dict[str, Any]) -> str:
    return _text(gap.get("gap_type"), UNKNOWN_TYPE)


def _owner_of(gap: dict[str, Any]) -> str:
    return _text(gap.get("owner"), UNKNOWN_OWNER)


def _ordered(counter: Counter[str]) -> dict[str, int]:
    """Counts as a dict ordered by descending count, then key — deterministic."""
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def _load_gaps(store: KuzuGraphStore) -> list[dict[str, Any]]:
    """Every ``:Gap`` node as a full dict (base cols + props) via ``get_node`` (§15.6)."""
    ids = [row[0] for row in store.rows("MATCH (n:Node) WHERE n.label='Gap' RETURN n.id")]
    gaps: list[dict[str, Any]] = []
    for gid in ids:
        node = store.get_node(gid)
        if node:
            gaps.append(node)
    return gaps


def _top_row(gap: dict[str, Any], score: float) -> dict[str, Any]:
    """One ranked-list entry: identity + priority score + RU explanation (§15.6)."""
    return {
        "id": gap.get("id"),
        "name": gap.get("name"),
        "gap_type": _type_of(gap),
        "domain": _domain_of(gap),
        "owner": _owner_of(gap),
        "score": score,
        "explanation": gap_explanation(gap),
    }


def build_gap_dashboard(store: KuzuGraphStore, *, top: int = 20) -> GapDashboard:
    """Aggregate all ``:Gap`` nodes into a prioritization dashboard (§15.6).

    Groups gaps by domain / type / owner, scores each with
    :func:`~kg_retrievers.gap_scoring.gap_priority_score`, and returns the top-N
    by priority (descending, ties stable). An empty store yields empty buckets, an
    empty ``top_gaps`` and zeroed totals. ``top`` caps the shortlist (``<= 0`` → none).
    """
    scored: list[tuple[dict[str, Any], float]] = [
        (gap, gap_priority_score(gap)) for gap in _load_gaps(store)
    ]
    by_domain = Counter(_domain_of(gap) for gap, _ in scored)
    by_type = Counter(_type_of(gap) for gap, _ in scored)
    by_owner = Counter(_owner_of(gap) for gap, _ in scored)
    # Stable sort by priority descending: equal-priority gaps keep insertion order.
    ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)
    limit = max(0, top)
    top_gaps = [_top_row(gap, score) for gap, score in ranked[:limit]]
    totals = {
        "gaps": len(scored),
        "domains": len(by_domain),
        "types": len(by_type),
        "owners": len(by_owner),
    }
    return GapDashboard(
        by_domain=_ordered(by_domain),
        by_type=_ordered(by_type),
        by_owner=_ordered(by_owner),
        top_gaps=top_gaps,
        totals=totals,
    )
