"""Per-domain graph summary over the Kuzu store (§24.25).

Сводка по предметной области: a compact, read-only snapshot of how much the graph
knows about one ``domain`` — how many technology solutions / methods, measurements
and gaps sit in it, plus the materials that domain touches most.

Everything is computed from queryable Kuzu *base* columns (``n.label`` and
``n.domain`` on the ``Node`` table, ``r`` on the ``Rel`` table) — never from the
JSON ``props`` catch-all, which Kuzu cannot filter on. ``top_materials`` ranks the
domain's ``Material`` nodes by their incident-edge degree (most connected first,
ties broken by display name), so the busiest materials float to the top. An
unknown/empty domain yields zero counts and no materials.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("domain_summary")

# Node labels that count as an answer "solution/method" (mirrors domain_templates).
SOLUTION_LABELS: tuple[str, ...] = ("TechnologySolution", "Method")

# How many top materials to keep by default.
DEFAULT_TOP_MATERIALS = 5


@dataclass(frozen=True)
class DomainSummary:
    """Read-only summary of one predметной области / domain (§24.25).

    - ``domain`` — the domain key this summary describes;
    - ``n_solutions`` — ``Node`` rows with a solution label (``TechnologySolution``
      / ``Method``) and ``domain`` equal to this domain;
    - ``n_measurements`` — ``Measurement`` nodes in this domain;
    - ``n_gaps`` — ``Gap`` nodes in this domain;
    - ``top_materials`` — ``(display_name, degree)`` pairs for the domain's
      ``Material`` nodes, most-connected first (ties by name), capped to ``top_k``.
    """

    domain: str
    n_solutions: int
    n_measurements: int
    n_gaps: int
    top_materials: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "n_solutions": self.n_solutions,
            "n_measurements": self.n_measurements,
            "n_gaps": self.n_gaps,
            "top_materials": [
                {"material": name, "degree": degree} for name, degree in self.top_materials
            ],
        }


def _count_by_label(store: KuzuGraphStore, labels: tuple[str, ...], domain: str) -> int:
    """Count ``Node`` rows in ``domain`` whose base ``label`` is one of ``labels``."""
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels AND n.domain=$domain RETURN count(n)",
        {"labels": list(labels), "domain": domain},
    )
    return int(rows[0][0]) if rows else 0


def _top_materials(store: KuzuGraphStore, domain: str, top_k: int) -> tuple[tuple[str, int], ...]:
    """Domain ``Material`` nodes ranked by incident-edge degree (base columns only).

    Reads ``canonical_name`` / ``name`` (both queryable base columns) for a stable
    display key and counts incident ``Rel`` edges via ``OPTIONAL MATCH`` so an
    isolated material still shows with degree ``0``. Sorted by degree desc, then
    display name asc; capped to ``top_k``.
    """
    rows = store.rows(
        "MATCH (m:Node) WHERE m.label='Material' AND m.domain=$domain "
        "OPTIONAL MATCH (m)-[r:Rel]-(:Node) "
        "RETURN m.id, m.canonical_name, m.name, count(r)",
        {"domain": domain},
    )
    ranked: list[tuple[str, int]] = []
    for node_id, canonical, name, degree in rows:
        display = canonical or name or node_id
        ranked.append((str(display), int(degree)))
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    return tuple(ranked[:top_k])


def domain_summary(
    store: KuzuGraphStore, domain: str, *, top_k: int = DEFAULT_TOP_MATERIALS
) -> DomainSummary:
    """Compute a :class:`DomainSummary` for ``domain`` over ``store`` (§24.25).

    Read-only. Counts come from the queryable base ``label`` / ``domain`` columns;
    materials are ranked by incident-edge degree. An unknown domain (or empty
    store) yields all-zero counts and no materials.
    """
    summary = DomainSummary(
        domain=domain,
        n_solutions=_count_by_label(store, SOLUTION_LABELS, domain),
        n_measurements=_count_by_label(store, ("Measurement",), domain),
        n_gaps=_count_by_label(store, ("Gap",), domain),
        top_materials=_top_materials(store, domain, top_k),
    )
    _log.info(
        "domain_summary.done",
        domain=domain,
        n_solutions=summary.n_solutions,
        n_measurements=summary.n_measurements,
        n_gaps=summary.n_gaps,
        n_materials=len(summary.top_materials),
    )
    return summary
