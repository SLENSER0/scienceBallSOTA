"""Edge relink & dedup planner for the §16.6 ``merge`` action (RU/EN).

Чистый планировщик (pure planner) — вычисляет, как переписать (relink) рёбра
при слиянии (merge) нескольких сущностей в одну каноническую, но **не выполняет**
никаких записей в граф. The curation-service merge relinks edges imperatively
against Kuzu; this module gives a side-effect-free counterpart so a merge can be
previewed, validated and diffed before any Kuzu write happens.

Rewriting rules (§16.6):

* any ``src``/``dst`` that appears in ``drop_ids`` is rewritten to
  ``canonical_id`` (перепривязка ребра к канонической сущности);
* an edge that becomes a self-loop (``src == dst``) *only because of* the
  rewrite is dropped and counted in ``self_loops_removed`` — a relation that was
  **already** a self-loop before the rewrite is kept (не считается удалённой);
* parallel duplicates keyed by ``(src, rel_type, dst)`` collapse to a single
  edge, each extra copy counted in ``duplicates_collapsed``.

Each edge is a mapping ``{src, rel_type, dst}``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def edge_key(e: Mapping) -> tuple:
    """Return the dedup key ``(src, rel_type, dst)`` for edge ``e`` (§16.6)."""
    return (str(e["src"]), str(e["rel_type"]), str(e["dst"]))


@dataclass(frozen=True)
class RelinkPlan:
    """Planned edge rewrite for one ``merge`` action (§16.6).

    План перепривязки рёбер при слиянии: ``kept_edges`` — итоговые уникальные
    рёбра после переписывания; ``dropped_edges`` — рёбра, отброшенные как
    самопетли (self-loops) либо схлопнутые дубликаты. Counters expose *why*:
    ``self_loops_removed`` — сколько рёбер стали самопетлями из-за rewrite;
    ``duplicates_collapsed`` — сколько параллельных копий схлопнуто.
    Every edge dict is ``{src, rel_type, dst}``.
    """

    kept_edges: list[dict]
    dropped_edges: list[dict]
    self_loops_removed: int
    duplicates_collapsed: int

    def as_dict(self) -> dict:
        """Return a JSON-friendly plain-``dict`` view (сериализуемый вид)."""
        return {
            "kept_edges": [dict(e) for e in self.kept_edges],
            "dropped_edges": [dict(e) for e in self.dropped_edges],
            "self_loops_removed": self.self_loops_removed,
            "duplicates_collapsed": self.duplicates_collapsed,
        }


def _rewrite(node_id: str, drop_ids: set[str], canonical_id: str) -> str:
    """Rewrite ``node_id`` to ``canonical_id`` iff it is a dropped id (§16.6)."""
    return canonical_id if node_id in drop_ids else node_id


def relink_edges(
    edges: Sequence[Mapping],
    drop_ids: set[str],
    canonical_id: str,
) -> RelinkPlan:
    """Compute a :class:`RelinkPlan` for merging ``drop_ids`` into ``canonical_id``.

    Переписывает любой ``src``/``dst`` из ``drop_ids`` в ``canonical_id``,
    отбрасывает возникшие самопетли и схлопывает параллельные дубликаты.
    Порядок: rewrite → drop new self-loops → collapse duplicates.
    """
    kept_edges: list[dict] = []
    dropped_edges: list[dict] = []
    self_loops_removed = 0
    duplicates_collapsed = 0
    seen: set[tuple] = set()

    for edge in edges:
        src = str(edge["src"])
        dst = str(edge["dst"])
        rel_type = str(edge["rel_type"])
        was_self_loop = src == dst

        new_src = _rewrite(src, drop_ids, canonical_id)
        new_dst = _rewrite(dst, drop_ids, canonical_id)
        rewritten = {"src": new_src, "rel_type": rel_type, "dst": new_dst}

        # Drop self-loops that appeared *because of* the rewrite (not pre-existing).
        if new_src == new_dst and not was_self_loop:
            self_loops_removed += 1
            dropped_edges.append(rewritten)
            continue

        key = edge_key(rewritten)
        if key in seen:
            duplicates_collapsed += 1
            dropped_edges.append(rewritten)
            continue

        seen.add(key)
        kept_edges.append(rewritten)

    return RelinkPlan(
        kept_edges=kept_edges,
        dropped_edges=dropped_edges,
        self_loops_removed=self_loops_removed,
        duplicates_collapsed=duplicates_collapsed,
    )
