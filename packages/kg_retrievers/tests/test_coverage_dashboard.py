"""Knowledge-coverage dashboard aggregation (§24.15).

Every assertion is hand-derivable. We seed three domains in a temp
:class:`KuzuGraphStore` (``domain`` and ``label`` are queryable base columns, so
the dashboard aggregates them directly — no ``get_node`` round-trip):

- **alpha**  — 3 Paper + 1 Document = 4 sources, 2 Measurement, 1 Gap, 1
  Contradiction. 4 sources ≥ 2 → well covered, *not* at risk.
- **beta**   — 1 Paper (1 source), 1 Measurement, 2 Gap. 1 source < 2 → high risk.
- **gamma**  — 1 Gap only, 0 sources → high risk.

So graph-wide: sources 5, measurements 3, gaps 4, contradictions 1 across 3
domains; the high-risk set is exactly {beta, gamma}.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.coverage_dashboard import (
    RISK_HIGH,
    RISK_OK,
    UNKNOWN_DOMAIN,
    CoverageDashboard,
    build_dashboard,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _node(store: KuzuGraphStore, nid: str, label: str, domain: str) -> None:
    store.upsert_node(nid, label, name=nid, domain=domain)


def _seed(store: KuzuGraphStore) -> None:
    # alpha: 4 sources (3 Paper + 1 Document), 2 Measurement, 1 Gap, 1 Contradiction.
    for i in range(1, 4):
        _node(store, f"paper:a{i}", "Paper", "alpha")
    _node(store, "doc:a1", "Document", "alpha")
    _node(store, "meas:a1", "Measurement", "alpha")
    _node(store, "meas:a2", "Measurement", "alpha")
    _node(store, "gap:a1", "Gap", "alpha")
    _node(store, "contra:a1", "Contradiction", "alpha")
    # beta: 1 source, 1 Measurement, 2 Gap → high risk.
    _node(store, "paper:b1", "Paper", "beta")
    _node(store, "meas:b1", "Measurement", "beta")
    _node(store, "gap:b1", "Gap", "beta")
    _node(store, "gap:b2", "Gap", "beta")
    # gamma: 1 Gap only, 0 sources → high risk.
    _node(store, "gap:g1", "Gap", "gamma")


def test_per_domain_counts_are_correct(store: KuzuGraphStore) -> None:
    _seed(store)
    dash = build_dashboard(store)
    by = {d.domain: d for d in dash.by_domain}
    assert [d.domain for d in dash.by_domain] == ["alpha", "beta", "gamma"]  # domain-ordered

    a = by["alpha"]
    assert (a.sources, a.measurements, a.gaps, a.contradictions) == (4, 2, 1, 1)
    assert a.risk == RISK_OK and a.at_risk is False

    b = by["beta"]
    assert (b.sources, b.measurements, b.gaps, b.contradictions) == (1, 1, 2, 0)
    assert b.risk == RISK_HIGH and b.at_risk is True

    g = by["gamma"]
    assert (g.sources, g.measurements, g.gaps, g.contradictions) == (0, 0, 1, 0)
    assert g.risk == RISK_HIGH and g.at_risk is True


def test_risk_domains_lists_low_source_domains(store: KuzuGraphStore) -> None:
    _seed(store)
    dash = build_dashboard(store)
    # exactly the sources<2 domains, sorted; the well-covered alpha is absent.
    assert dash.risk_domains == ("beta", "gamma")
    assert "alpha" not in dash.risk_domains
    assert set(dash.risk_domains) == {d.domain for d in dash.by_domain if d.at_risk}


def test_totals_sum_the_per_domain_rows(store: KuzuGraphStore) -> None:
    _seed(store)
    dash = build_dashboard(store)
    assert dash.totals == {
        "domains": 3,
        "risk_domains": 2,
        "sources": 5,
        "measurements": 3,
        "gaps": 4,
        "contradictions": 1,
    }
    # each category total equals the sum of the per-domain rows.
    for category in ("sources", "measurements", "gaps", "contradictions"):
        assert dash.totals[category] == sum(getattr(d, category) for d in dash.by_domain)
    assert dash.totals["domains"] == len(dash.by_domain)
    assert dash.totals["risk_domains"] == len(dash.risk_domains)


def test_empty_store_yields_zeros(store: KuzuGraphStore) -> None:
    dash = build_dashboard(store)
    assert isinstance(dash, CoverageDashboard)
    assert dash.by_domain == ()
    assert dash.risk_domains == ()
    assert dash.totals == {
        "domains": 0,
        "risk_domains": 0,
        "sources": 0,
        "measurements": 0,
        "gaps": 0,
        "contradictions": 0,
    }


def test_well_covered_domain_is_not_flagged(store: KuzuGraphStore) -> None:
    _seed(store)
    dash = build_dashboard(store)
    alpha = next(d for d in dash.by_domain if d.domain == "alpha")
    assert alpha.sources >= 2  # four distinct sources back this domain
    assert alpha.at_risk is False
    assert alpha.risk == RISK_OK
    assert alpha.domain not in dash.risk_domains


def test_untracked_labels_excluded_and_undomained_bucketed(store: KuzuGraphStore) -> None:
    # A Material is not a tracked coverage label → it never inflates any count,
    # so its 'alpha' domain (which has no tracked node) does not appear at all.
    _node(store, "mat:1", "Material", "alpha")
    # A Paper with no domain column lands in the RU fallback bucket, still a source.
    store.upsert_node("paper:x", "Paper", name="источник без домена")
    dash = build_dashboard(store)
    by = {d.domain: d for d in dash.by_domain}
    assert "alpha" not in by
    assert set(by) == {UNKNOWN_DOMAIN}
    fallback = by[UNKNOWN_DOMAIN]
    assert (fallback.sources, fallback.measurements, fallback.gaps) == (1, 0, 0)
    assert fallback.at_risk is True  # one source < 2
    assert dash.totals["sources"] == 1


def test_as_dict_round_trips_all_sections(store: KuzuGraphStore) -> None:
    _seed(store)
    d = build_dashboard(store).as_dict()
    assert set(d) == {"by_domain", "totals", "risk_domains"}
    assert isinstance(d["by_domain"], list) and isinstance(d["risk_domains"], list)
    assert d["risk_domains"] == ["beta", "gamma"]
    assert d["totals"]["sources"] == 5
    alpha_row = next(r for r in d["by_domain"] if r["domain"] == "alpha")
    assert set(alpha_row) == {
        "domain",
        "sources",
        "measurements",
        "gaps",
        "contradictions",
        "risk",
    }
    assert alpha_row["sources"] == 4 and alpha_row["risk"] == RISK_OK
