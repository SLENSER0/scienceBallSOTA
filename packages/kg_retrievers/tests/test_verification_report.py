"""§24.7 — knowledge_verification_report + is_source_obsolete.

Проверяем на временном Kuzu-хранилище: доли статусов верификации по домену
(суммируются в 1.0), фильтр по домену, агрегированные totals, устаревание
источников (стандарт/патент старше порога), и форму ``as_dict``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.verification_report import (
    STATUSES,
    is_source_obsolete,
    knowledge_verification_report,
)

NOW = "2026-07-03"


def _new_store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _add_fact(
    store: KuzuGraphStore,
    key: str,
    *,
    domain: str,
    status: str | None = None,
    label: str = "Measurement",
) -> str:
    """Seed a fact node; ``status`` (a custom, non-column prop) may be omitted."""
    nid = make_id(label, key)
    props: dict[str, object] = {"name": key, "domain": domain}
    if status is not None:
        props["verification_status"] = status
    store.upsert_node(nid, label, **props)
    return nid


def _add_source(
    store: KuzuGraphStore,
    key: str,
    *,
    label: str = "Standard",
    year: int | None = None,
    effective_date: str | None = None,
) -> dict:
    nid = make_id(label, key)
    props: dict[str, object] = {"name": key}
    if year is not None:
        props["year"] = year
    if effective_date is not None:
        props["effective_date"] = effective_date
    store.upsert_node(nid, label, **props)
    node = store.get_node(nid)
    assert node is not None
    return node


# ---------------------------------------------------------------------------
# knowledge_verification_report
# ---------------------------------------------------------------------------
def test_mixed_statuses_shares_sum_to_one() -> None:
    # pyro domain: 2 verified, 1 reviewed, 1 obsolete, 1 missing(→pending) = 5 facts.
    store = _new_store()
    _add_fact(store, "m1", domain="pyro", status="verified")
    _add_fact(store, "m2", domain="pyro", status="verified")
    _add_fact(store, "m3", domain="pyro", status="reviewed")
    _add_fact(store, "m4", domain="pyro", status="obsolete")
    _add_fact(store, "m5", domain="pyro")  # no status → pending
    rep = knowledge_verification_report(store)
    pyro = rep.by_domain["pyro"]
    assert pyro["total"] == 5
    assert pyro["counts"] == {"verified": 2, "reviewed": 1, "pending": 1, "obsolete": 1}
    assert pyro["shares"]["verified"] == pytest.approx(0.4)
    assert pyro["shares"]["reviewed"] == pytest.approx(0.2)
    assert pyro["shares"]["pending"] == pytest.approx(0.2)
    assert pyro["shares"]["obsolete"] == pytest.approx(0.2)
    assert sum(pyro["shares"].values()) == pytest.approx(1.0)
    store.close()


def test_missing_status_treated_as_pending() -> None:
    store = _new_store()
    _add_fact(store, "only", domain="hydro")  # no verification_status at all
    rep = knowledge_verification_report(store)
    hydro = rep.by_domain["hydro"]
    assert hydro["counts"]["pending"] == 1
    assert hydro["shares"]["pending"] == pytest.approx(1.0)
    assert hydro["shares"]["verified"] == 0.0
    store.close()


def test_domain_filter_scopes_to_one_domain() -> None:
    store = _new_store()
    _add_fact(store, "a", domain="pyro", status="verified")
    _add_fact(store, "b", domain="hydro", status="verified")
    _add_fact(store, "c", domain="hydro", status="pending")
    # TechnologySolution is also a fact label and must be counted.
    _add_fact(store, "t", domain="hydro", status="reviewed", label="TechnologySolution")
    rep = knowledge_verification_report(store, domain="hydro")
    assert set(rep.by_domain) == {"hydro"}  # pyro excluded by the filter
    hydro = rep.by_domain["hydro"]
    assert hydro["total"] == 3
    assert hydro["counts"] == {"verified": 1, "reviewed": 1, "pending": 1, "obsolete": 0}
    assert rep.totals["total"] == 3  # totals reflect only the filtered facts
    store.close()


def test_empty_domain_yields_zeros() -> None:
    store = _new_store()
    _add_fact(store, "a", domain="pyro", status="verified")  # different domain
    rep = knowledge_verification_report(store, domain="no_such_domain")
    entry = rep.by_domain["no_such_domain"]  # requested domain always present
    assert entry["total"] == 0
    assert entry["counts"] == {"verified": 0, "reviewed": 0, "pending": 0, "obsolete": 0}
    assert all(v == 0.0 for v in entry["shares"].values())
    assert rep.totals["total"] == 0
    store.close()


def test_totals_aggregate_across_domains() -> None:
    store = _new_store()
    _add_fact(store, "a", domain="pyro", status="verified")
    _add_fact(store, "b", domain="pyro", status="obsolete")
    _add_fact(store, "c", domain="hydro", status="verified")
    _add_fact(store, "d", domain="hydro", status="reviewed")
    rep = knowledge_verification_report(store)
    assert set(rep.by_domain) == {"hydro", "pyro"}
    # totals = element-wise sum of both domains' counts.
    assert rep.totals["total"] == 4
    assert rep.totals["counts"] == {"verified": 2, "reviewed": 1, "pending": 0, "obsolete": 1}
    assert rep.totals["shares"]["verified"] == pytest.approx(0.5)
    assert sum(rep.totals["shares"].values()) == pytest.approx(1.0)
    store.close()


def test_fact_without_domain_grouped_under_unknown() -> None:
    store = _new_store()
    nid = make_id("Measurement", "orphan")
    store.upsert_node(nid, "Measurement", name="orphan", verification_status="verified")
    rep = knowledge_verification_report(store)
    assert "unknown" in rep.by_domain
    assert rep.by_domain["unknown"]["counts"]["verified"] == 1
    store.close()


def test_as_dict_shape() -> None:
    store = _new_store()
    _add_fact(store, "a", domain="pyro", status="verified")
    rep = knowledge_verification_report(store)
    d = rep.as_dict()
    assert set(d) == {"by_domain", "totals"}
    assert set(d["totals"]) == {"total", "counts", "shares"}
    assert tuple(d["totals"]["counts"]) == STATUSES
    assert set(d["totals"]["shares"]) == set(STATUSES)
    assert d["by_domain"]["pyro"]["counts"]["verified"] == 1
    store.close()


# ---------------------------------------------------------------------------
# is_source_obsolete
# ---------------------------------------------------------------------------
def test_obsolete_standard_detected_past_max_age() -> None:
    store = _new_store()
    old = _add_source(store, "old-std", year=2000)  # 26 years before NOW
    assert is_source_obsolete(old, now_iso=NOW, max_age_years=10) is True
    store.close()


def test_obsolete_by_effective_date() -> None:
    store = _new_store()
    node = _add_source(store, "old-patent", label="Patent", effective_date="2005-06-01")
    assert is_source_obsolete(node, now_iso=NOW, max_age_years=10) is True
    store.close()


def test_recent_standard_not_flagged() -> None:
    store = _new_store()
    recent = _add_source(store, "recent-std", year=2024)  # 2 years before NOW
    assert is_source_obsolete(recent, now_iso=NOW, max_age_years=10) is False
    store.close()


def test_non_source_label_never_obsolete() -> None:
    store = _new_store()
    # A Measurement is not a Standard/Patent, so it is never a stale source.
    nid = make_id("Measurement", "old-meas")
    store.upsert_node(nid, "Measurement", name="old-meas", year=1990)
    node = store.get_node(nid)
    assert node is not None
    assert is_source_obsolete(node, now_iso=NOW, max_age_years=5) is False
    store.close()


def test_source_without_date_not_obsolete() -> None:
    store = _new_store()
    node = _add_source(store, "undated-std")  # neither year nor effective_date
    assert is_source_obsolete(node, now_iso=NOW, max_age_years=1) is False
    store.close()
