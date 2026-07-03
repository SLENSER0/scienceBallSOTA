"""Techno-economic comparison over the seed graph (§24.11).

Hand-checked against ``kg_retrievers.seed.build_seed_graph`` (§seed-4, deep-well
injection):
- the ``TechnologySolution`` ``tech:deep-well-injection-russia`` (inj_ru) carries a
  ``HAS_TECHNOECONOMIC_INDICATOR`` edge to ``TechnoEconomicIndicator``
  ``tei:injection-capex-ru`` with ``property_name='capex'``, value 5.0, unit MUSD;
- that CAPEX indicator is ``SUPPORTED_BY`` Evidence
  ``ev:injection-2020-pdf-inj-capex`` (ev_inj);
- both injection solutions live in ``domain='environment'``.

The seed defines exactly one techno-economic indicator, so the multi-row ranking
test upserts a second CAPEX indicator on the Canada solution (store API only — no
seed/graph_store files are edited).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph
from kg_retrievers.technoeconomic import (
    TECHNOECONOMIC_PROPERTIES,
    TechnoEconomicComparison,
    TechnoEconomicIndicatorRow,
    compare_technoeconomics,
    rank_by_indicator,
)

INJ_RU = make_id("TechnologySolution", "deep well injection russia")
INJ_CA = make_id("TechnologySolution", "deep well injection canada")
CAPEX = make_id("TechnoEconomicIndicator", "injection capex ru")
EV_INJ = make_id("Evidence", "injection-2020.pdf:inj-capex")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _capex_row(comparison: TechnoEconomicComparison) -> TechnoEconomicIndicatorRow:
    return next(r for r in comparison.indicators if r.indicator_id == CAPEX)


def test_comparison_finds_at_least_one_indicator(store: KuzuGraphStore) -> None:
    comparison = compare_technoeconomics(store)
    assert comparison.count >= 1
    # every seed TechnologySolution is listed as an in-scope solution (8 of them)
    assert INJ_RU in comparison.solutions
    assert len(comparison.solutions) == 8
    # the only seed indicator is the deep-well-injection CAPEX
    assert {r.indicator for r in comparison.indicators} == {"capex"}


def test_capex_value_present_with_its_solution(store: KuzuGraphStore) -> None:
    row = _capex_row(compare_technoeconomics(store))
    assert row.indicator == "capex"
    assert row.value == 5.0
    assert row.unit == "MUSD"
    # the CAPEX belongs to the Russia deep-well-injection solution
    assert row.solution_id == INJ_RU
    # as_dict exposes exactly the §24.11 row shape
    d = row.as_dict()
    assert set(d) == {"solution_id", "indicator", "value", "unit", "evidence_ids"}
    assert d["value"] == 5.0
    assert d["solution_id"] == INJ_RU


def test_by_indicator_is_keyed(store: KuzuGraphStore) -> None:
    comparison = compare_technoeconomics(store)
    assert "capex" in comparison.by_indicator
    assert "capex" in TECHNOECONOMIC_PROPERTIES
    # the CAPEX row is grouped under its indicator key
    capex_rows = comparison.by_indicator["capex"]
    assert [r.indicator_id for r in capex_rows] == [CAPEX]
    # comparison.as_dict() mirrors the grouping
    d = comparison.as_dict()
    assert set(d) == {"solutions", "indicators", "by_indicator"}
    assert d["by_indicator"]["capex"][0]["solution_id"] == INJ_RU


def test_rank_by_indicator_orders(store: KuzuGraphStore) -> None:
    # add a cheaper CAPEX (3.0 MUSD) on the Canada solution via the store API
    store.upsert_node(
        CAPEX + ":ca",
        "TechnoEconomicIndicator",
        name="CAPEX закачки (Канада)",
        property_name="capex",
        value_normalized=3.0,
        normalized_unit="MUSD",
    )
    store.upsert_edge(INJ_CA, CAPEX + ":ca", "HAS_TECHNOECONOMIC_INDICATOR", confidence=0.7)

    comparison = compare_technoeconomics(store)
    ranked = rank_by_indicator(comparison, "capex", ascending=True)
    assert [r.value for r in ranked] == [3.0, 5.0]
    assert ranked[0].solution_id == INJ_CA  # cheapest CAPEX first

    ranked_desc = rank_by_indicator(comparison, "capex", ascending=False)
    assert [r.value for r in ranked_desc] == [5.0, 3.0]
    # ranking an indicator absent from the comparison is graceful
    assert rank_by_indicator(comparison, "opex") == []


def test_capex_indicator_has_linked_evidence(store: KuzuGraphStore) -> None:
    row = _capex_row(compare_technoeconomics(store))
    assert row.evidence_ids  # non-empty
    assert EV_INJ in row.evidence_ids
    # evidence flows through into the serialised row too
    assert EV_INJ in row.as_dict()["evidence_ids"]


def test_domain_scoping(store: KuzuGraphStore) -> None:
    # both injection solutions are environment-domain → CAPEX survives the scope
    env = compare_technoeconomics(store, domain="environment")
    assert env.count >= 1
    assert INJ_RU in env.solutions
    # environment has exactly three solutions: inj_ru, inj_ca, wet-scrubber
    assert len(env.solutions) == 3
    assert _capex_row(env).value == 5.0
    # a solution domain that does not carry the CAPEX drops it (still graceful)
    water = compare_technoeconomics(store, domain="water_treatment")
    assert water.indicators == ()
    assert INJ_RU not in water.solutions


def test_empty_and_absent_domain_are_graceful(
    store: KuzuGraphStore, empty_store: KuzuGraphStore
) -> None:
    # a graph with no solutions/indicators yields an empty comparison
    empty = compare_technoeconomics(empty_store)
    assert empty.count == 0
    assert empty.solutions == ()
    assert empty.indicators == ()
    assert empty.by_indicator == {}
    assert empty.as_dict()["indicators"] == []
    # a domain that exists nowhere is equally graceful (no error, empty result)
    absent = compare_technoeconomics(store, domain="no_such_domain")
    assert absent.count == 0
    assert absent.solutions == ()
    assert absent.by_indicator == {}
