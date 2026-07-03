"""Knowledge-coverage dashboard aggregation (§24.15).

A per-domain rollup a curator uses to see, at a glance, where the knowledge graph
is *thin*: for every research domain (домен) it counts the evidence that backs it
— **sources** (Paper / Document), **measurements** (наблюдения), **gaps** (пробелы)
and **contradictions** (противоречия) — and raises a *high-risk* flag on any domain
resting on fewer than :data:`MIN_SOURCES` distinct sources. A domain with one paper
(or none) is a coverage risk regardless of how many gaps or measurements hang off it.

:func:`build_dashboard` reads a :class:`~kg_retrievers.graph_store.KuzuGraphStore`,
groups the tracked node labels by their ``domain`` and rolls them into a frozen
:class:`CoverageDashboard` with:

- **by_domain** — one :class:`DomainCoverage` per domain (domain-ordered), each with
  its four counts плюс a risk flag;
- **risk_domains** — итог: the sorted names of the high-risk domains (sources < 2);
- **totals** — the domain count and the graph-wide sum of every category, so the
  totals sum exactly matches the per-domain rows.

Kuzu note: both ``domain`` and ``label`` are real queryable base columns of the
generic ``Node`` table, so the aggregation is a single grouped ``count`` — no custom
prop is read, hence no ``get_node`` round-trip is needed here (§3 / ADR-0005).

Strictly read-only: it never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("coverage_dashboard")

# RU fallback bucket for tracked nodes carrying no ``domain`` column (§24.15).
UNKNOWN_DOMAIN = "без домена"

# A domain resting on fewer than this many sources is flagged high-risk (§24.15).
MIN_SOURCES = 2

# Risk flag values: high (недостаточно источников) vs ok (достаточно покрыт).
RISK_HIGH = "high"
RISK_OK = "ok"

# Node labels tracked per domain, each mapped to its dashboard count category.
# Sources are the primary-literature nodes (Paper / Document) that ground a domain.
_CATEGORY_OF: dict[str, str] = {
    "Paper": "sources",
    "Document": "sources",
    "Measurement": "measurements",
    "Gap": "gaps",
    "Contradiction": "contradictions",
}
TRACKED_LABELS: tuple[str, ...] = tuple(_CATEGORY_OF)
_CATEGORIES: tuple[str, ...] = ("sources", "measurements", "gaps", "contradictions")


@dataclass(frozen=True)
class DomainCoverage:
    """One domain's coverage counts plus its risk flag (§24.15).

    ``sources`` counts Paper / Document nodes; ``measurements`` / ``gaps`` /
    ``contradictions`` count their like-labelled nodes. ``risk`` is :data:`RISK_HIGH`
    when ``sources < MIN_SOURCES`` (домен слабо покрыт), else :data:`RISK_OK`.
    """

    domain: str
    sources: int
    measurements: int
    gaps: int
    contradictions: int
    risk: str

    @property
    def at_risk(self) -> bool:
        """True when this domain is flagged high-risk (too few sources)."""
        return self.risk == RISK_HIGH

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "sources": self.sources,
            "measurements": self.measurements,
            "gaps": self.gaps,
            "contradictions": self.contradictions,
            "risk": self.risk,
        }


@dataclass(frozen=True)
class CoverageDashboard:
    """Per-domain coverage rollup over the graph (§24.15).

    ``by_domain`` is domain-ordered :class:`DomainCoverage` rows; ``risk_domains`` is
    the sorted names of the high-risk domains; ``totals`` holds the domain count and
    the graph-wide sum of every category (summing the ``by_domain`` rows exactly).
    """

    by_domain: tuple[DomainCoverage, ...] = ()
    totals: dict[str, int] = field(default_factory=dict)
    risk_domains: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "by_domain": [d.as_dict() for d in self.by_domain],
            "totals": dict(self.totals),
            "risk_domains": list(self.risk_domains),
        }


def _domain_key(domain: object) -> str:
    """A trimmed non-empty domain name, else the RU fallback bucket label."""
    if isinstance(domain, str) and domain.strip():
        return domain.strip()
    return UNKNOWN_DOMAIN


def _empty_counts() -> dict[str, int]:
    return dict.fromkeys(_CATEGORIES, 0)


def _load_domain_counts(store: KuzuGraphStore) -> list[tuple[object, str, int]]:
    """(domain, label, n) triples for every tracked node, grouped in one query (§24.15).

    ``domain`` and ``label`` are base columns, so a single grouped ``count`` suffices;
    a tracked node with a NULL ``domain`` yields a ``None`` domain (→ fallback bucket).
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels RETURN n.domain, n.label, count(n)",
        {"labels": list(TRACKED_LABELS)},
    )
    return [(r[0], r[1], int(r[2])) for r in rows]


def _domain_coverage(domain: str, counts: dict[str, int]) -> DomainCoverage:
    sources = counts["sources"]
    risk = RISK_HIGH if sources < MIN_SOURCES else RISK_OK
    return DomainCoverage(
        domain=domain,
        sources=sources,
        measurements=counts["measurements"],
        gaps=counts["gaps"],
        contradictions=counts["contradictions"],
        risk=risk,
    )


def build_dashboard(store: KuzuGraphStore) -> CoverageDashboard:
    """Aggregate the graph into a per-domain knowledge-coverage dashboard (§24.15).

    Groups Paper/Document (sources), Measurement, Gap and Contradiction nodes by their
    ``domain`` — tracked nodes without a domain fall into the RU :data:`UNKNOWN_DOMAIN`
    bucket — and flags every domain with fewer than :data:`MIN_SOURCES` sources as
    high-risk. ``by_domain`` and ``risk_domains`` are domain-name ordered; ``totals``
    sums the rows. An empty graph yields no domains and zeroed totals.
    """
    buckets: dict[str, dict[str, int]] = {}
    for domain, label, n in _load_domain_counts(store):
        counts = buckets.setdefault(_domain_key(domain), _empty_counts())
        counts[_CATEGORY_OF[label]] += n

    by_domain = tuple(_domain_coverage(name, buckets[name]) for name in sorted(buckets))
    risk_domains = tuple(d.domain for d in by_domain if d.at_risk)
    totals = {"domains": len(by_domain), "risk_domains": len(risk_domains)}
    for category in _CATEGORIES:
        totals[category] = sum(getattr(d, category) for d in by_domain)

    _log.info("coverage_dashboard.built", **totals)
    return CoverageDashboard(by_domain=by_domain, totals=totals, risk_domains=risk_domains)
