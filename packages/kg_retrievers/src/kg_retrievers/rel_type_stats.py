"""Relationship-type frequency stats over a Kuzu graph store (§8.15).

Статистика типов рёбер — counts how many ``Rel`` edges carry each relationship
type and reports the totals plus a ranking of the most common types. The edge
``type`` is a base column on the generic ``Rel`` table (see ``graph_store.py``),
so it is read straight from the query result; no per-edge ``props`` lookup is
needed.

Read-only: this module never writes to the graph. Результат — frozen dataclass
with ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.graph_store import KuzuGraphStore


@dataclass(frozen=True)
class RelTypeStats:
    """Edge counts grouped by relationship type (§8.15).

    - ``by_type`` — relationship type -> number of ``Rel`` edges of that type;
    - ``total`` — total edge count (sum of ``by_type`` values);
    - ``top`` — ``(type, count)`` pairs sorted by count desc, then type asc.
    """

    by_type: dict[str, int]
    total: int
    top: tuple[tuple[str, int], ...]

    @property
    def top_type(self) -> str | None:
        """Most frequent relationship type, or ``None`` for an empty graph."""
        return self.top[0][0] if self.top else None

    def as_dict(self) -> dict:
        return {
            "by_type": dict(self.by_type),
            "total": self.total,
            "top": [[t, c] for t, c in self.top],
        }


def rel_type_stats(store: KuzuGraphStore) -> RelTypeStats:
    """Count ``Rel`` edges by relationship type over the whole store (§8.15).

    Подсчёт рёбер по типу связи. Reads the base ``r.type`` column and aggregates
    in Cypher; the ranking is stable (count desc, then type name asc).
    """
    rows = store.rows("MATCH ()-[r:Rel]->() RETURN r.type, count(r)")
    by_type: dict[str, int] = {t: int(c) for t, c in rows if t is not None}
    total = sum(by_type.values())
    top = tuple(sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])))
    return RelTypeStats(by_type=by_type, total=total, top=top)
