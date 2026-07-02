"""Domain query templates over the seed graph (§24.9 / §12).

Each of the six templates is exercised against the deterministic seed graph and
asserted on real behaviour: the expected solutions/measurements surface, evidence
is collected via declared edges, and a non-empty ``GraphResponse`` subgraph is
returned.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import GraphResponse
from kg_retrievers.domain_templates import (
    cold_climate_heap_leaching,
    mine_water_deep_injection,
    nickel_catholyte_circulation_solutions,
    precious_metals_partitioning,
    so2_removal_methods,
    water_desalination_suitability,
)
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    st = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(st)
    yield st
    st.close()


def _names(store: KuzuGraphStore, ids: list[str]) -> str:
    return " ".join((store.get_node(i) or {}).get("name", "") for i in ids).lower()


def _props(store: KuzuGraphStore, ids: list[str]) -> set[str]:
    return {(store.get_node(i) or {}).get("property_name", "") for i in ids}


def _assert_subgraph(res: dict) -> None:
    assert isinstance(res["graph"], GraphResponse)
    assert res["graph"].nodes  # non-empty payload for the UI


# ---------------------------------------------------------------------
# 1) water desalination — RO must appear
# ---------------------------------------------------------------------
def test_water_desalination_suitability(store: KuzuGraphStore) -> None:
    res = water_desalination_suitability(
        store, ions=["SO4", "Cl", "Ca", "Mg", "Na"], target_tds=1000.0
    )
    assert res["solutions"]
    assert "осмос" in _names(store, res["solutions"])  # reverse osmosis (RO) surfaces
    # ion + TDS-target measurements about the water are gathered
    assert "total_dissolved_solids" in _props(store, res["measurements"])
    assert "concentration" in _props(store, res["measurements"])
    assert res["target_tds"] == 1000.0
    assert res["target_tds_met"] is True  # seeded TDS target (1000) meets the request
    assert res["evidence"]  # evidence-first: RO is source-backed
    _assert_subgraph(res)


def test_water_desalination_ion_filter(store: KuzuGraphStore) -> None:
    # Narrowing the ion list must reduce the returned ion measurements.
    full = water_desalination_suitability(
        store, ions=["SO4", "Cl", "Ca", "Mg", "Na"], target_tds=1000.0
    )
    one = water_desalination_suitability(store, ions=["SO4"], target_tds=1000.0)
    assert len(one["measurements"]) < len(full["measurements"])
    # a tighter target is not met by the seeded 1000 mg/L target
    strict = water_desalination_suitability(store, ions=["SO4"], target_tds=500.0)
    assert strict["target_tds_met"] is False


def test_water_ion_filter_no_substring_overmatch(store: KuzuGraphStore) -> None:
    # regression: "Co"/"Ti" are substrings of the property name "concentration";
    # matching against property_name over-selected every ion. An absent ion must
    # return only the TDS-target measurement, not all ion rows.
    full = water_desalination_suitability(
        store, ions=["SO4", "Cl", "Ca", "Mg", "Na"], target_tds=1000.0
    )
    cobalt = water_desalination_suitability(store, ions=["Co"], target_tds=1000.0)
    assert len(cobalt["measurements"]) < len(full["measurements"])
    # only the TDS-target Measurement remains (no cobalt ion measurement is seeded)
    assert "concentration" not in _props(store, cobalt["measurements"])
    assert "total_dissolved_solids" in _props(store, cobalt["measurements"])


# ---------------------------------------------------------------------
# 2) nickel catholyte — flow_velocity + contradiction
# ---------------------------------------------------------------------
def test_nickel_catholyte_circulation(store: KuzuGraphStore) -> None:
    res = nickel_catholyte_circulation_solutions(store)
    assert res["solutions"]
    assert "flow_velocity" in _props(store, res["measurements"])
    # the 0.2 vs 0.5 m/s catholyte-velocity contradiction is surfaced
    assert res["contradictions"]
    # applies to nickel
    assert "никель" in _names(store, res["materials"]) or "католит" in _names(
        store, res["materials"]
    )
    _assert_subgraph(res)


# ---------------------------------------------------------------------
# 3) precious metals partitioning — distribution coefficients + year filter
# ---------------------------------------------------------------------
def test_precious_metals_partitioning(store: KuzuGraphStore) -> None:
    res = precious_metals_partitioning(store, years=5)
    assert res["measurements"]
    assert _props(store, res["measurements"]) == {"distribution_coefficient"}
    # phases (matte + slag) present
    assert len(res["materials"]) >= 2
    assert res["evidence"]
    _assert_subgraph(res)


def test_precious_metals_year_filter_excludes_old(store: KuzuGraphStore) -> None:
    # The supporting paper is 2023; a 1-year window (cutoff 2025) drops everything.
    res = precious_metals_partitioning(store, years=1)
    assert res["measurements"] == []
    # without a window, all coefficients are returned
    res_all = precious_metals_partitioning(store, years=None)
    assert len(res_all["measurements"]) >= 3


# ---------------------------------------------------------------------
# 4) mine water deep injection — RU vs foreign practice
# ---------------------------------------------------------------------
def test_mine_water_deep_injection(store: KuzuGraphStore) -> None:
    res = mine_water_deep_injection(store)
    assert res["solutions"]
    assert res["facilities"]  # injection well
    assert res["indicators"]  # CAPEX techno-economic indicator
    grouped = res["grouped_by_practice"]
    assert "russia" in grouped and "foreign" in grouped  # comparison across practice
    assert res["evidence"]
    _assert_subgraph(res)


# ---------------------------------------------------------------------
# 5) SO2 removal — scrubber, water methods must NOT leak in
# ---------------------------------------------------------------------
def test_so2_removal_methods(store: KuzuGraphStore) -> None:
    res = so2_removal_methods(store)
    assert res["solutions"]
    names = _names(store, res["solutions"])
    assert "скруббер" in names or "сероочистка" in names
    assert "осмос" not in names  # RO (water) does not leak into a gas query
    assert "removal_efficiency" in _props(store, res["measurements"])
    _assert_subgraph(res)


# ---------------------------------------------------------------------
# 6) cold-climate heap leaching — knowledge gap
# ---------------------------------------------------------------------
def test_cold_climate_heap_leaching(store: KuzuGraphStore) -> None:
    res = cold_climate_heap_leaching(store)
    assert res["solutions"]  # the heap-leaching regime
    assert res["gaps"]  # the knowledge gap is the answer
    assert "никель" in _names(store, res["materials"])  # applies to nickel ore
    _assert_subgraph(res)
