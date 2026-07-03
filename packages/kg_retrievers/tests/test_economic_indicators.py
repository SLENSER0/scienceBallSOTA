"""Techno-economic indicator extraction over a temp Kuzu store (§24.22).

Hand-checked against a hand-built graph: one ``TechnologySolution`` (``tech:sol-a``)
carries four ``HAS_TECHNOECONOMIC_INDICATOR`` edges to ``TechnoEconomicIndicator``
nodes — capex 5.0 MUSD (with a note), opex 1.2 MUSD/y, npv 12.5 MUSD and a
``payback_period`` of 3.0 years (which normalises to kind ``payback``). A second
solution (``tech:sol-b``) has no indicators.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.economic_indicators import (
    KNOWN_KINDS,
    EconomicIndicator,
    indicators_for,
)
from kg_retrievers.graph_store import KuzuGraphStore

SOL_A = "tech:sol-a"
SOL_B = "tech:sol-b"
CAPEX_NOTE = "капитальные затраты / capital expenditure"


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    s.upsert_node(SOL_A, "TechnologySolution", name="Solution A", domain="environment")
    s.upsert_node(SOL_B, "TechnologySolution", name="Solution B", domain="environment")
    s.upsert_node(
        "tei:capex-a",
        "TechnoEconomicIndicator",
        name="CAPEX",
        property_name="capex",
        value_normalized=5.0,
        normalized_unit="MUSD",
        note=CAPEX_NOTE,
    )
    s.upsert_node(
        "tei:opex-a",
        "TechnoEconomicIndicator",
        name="OPEX",
        property_name="opex",
        value_normalized=1.2,
        normalized_unit="MUSD/y",
    )
    s.upsert_node(
        "tei:npv-a",
        "TechnoEconomicIndicator",
        name="NPV",
        property_name="npv",
        value_normalized=12.5,
        normalized_unit="MUSD",
    )
    s.upsert_node(
        "tei:payback-a",
        "TechnoEconomicIndicator",
        name="Payback",
        property_name="payback_period",
        value_normalized=3.0,
        normalized_unit="years",
    )
    for iid in ("tei:capex-a", "tei:opex-a", "tei:npv-a", "tei:payback-a"):
        s.upsert_edge(SOL_A, iid, "HAS_TECHNOECONOMIC_INDICATOR", confidence=0.8)
    yield s
    s.close()


def _by_kind(store: KuzuGraphStore, kind: str) -> EconomicIndicator:
    return next(i for i in indicators_for(store, SOL_A) if i.kind == kind)


def test_capex_indicator_returned(store: KuzuGraphStore) -> None:
    capex = _by_kind(store, "capex")
    assert capex.kind == "capex"
    assert capex.value == 5.0
    assert capex.unit == "MUSD"
    # the free-text note is a custom prop read back via get_node
    assert capex.note == CAPEX_NOTE


def test_opex_indicator_returned(store: KuzuGraphStore) -> None:
    opex = _by_kind(store, "opex")
    assert opex.kind == "opex"
    assert opex.value == 1.2
    assert opex.unit == "MUSD/y"
    # no note was attached to the opex node
    assert opex.note is None


def test_unknown_solution_returns_empty(store: KuzuGraphStore) -> None:
    # a solution id absent from the graph yields no indicators
    assert indicators_for(store, "tech:does-not-exist") == []
    # a solution present but with no indicator edges is equally empty
    assert indicators_for(store, SOL_B) == []


def test_value_and_unit(store: KuzuGraphStore) -> None:
    # property_name 'payback_period' normalises to kind 'payback'
    payback = _by_kind(store, "payback")
    assert payback.kind == "payback"
    assert payback.value == 3.0
    assert payback.unit == "years"
    # npv carries its own value + unit independently
    npv = _by_kind(store, "npv")
    assert npv.value == 12.5
    assert npv.unit == "MUSD"


def test_multiple_indicators(store: KuzuGraphStore) -> None:
    inds = indicators_for(store, SOL_A)
    assert len(inds) == 4
    # deterministic order by indicator node id: capex < npv < opex < payback
    assert [i.kind for i in inds] == ["capex", "npv", "opex", "payback"]
    # every returned kind is a recognised techno-economic kind
    assert all(i.kind in KNOWN_KINDS for i in inds)


def test_unrecognised_kind_skipped(store: KuzuGraphStore) -> None:
    # an indicator whose property_name is not techno-economic is dropped
    store.upsert_node(
        "tei:sec-a",
        "TechnoEconomicIndicator",
        name="Specific energy",
        property_name="specific_energy_consumption",
        value_normalized=42.0,
        normalized_unit="kWh/t",
    )
    store.upsert_edge(SOL_A, "tei:sec-a", "HAS_TECHNOECONOMIC_INDICATOR")
    kinds = [i.kind for i in indicators_for(store, SOL_A)]
    assert "specific_energy_consumption" not in kinds
    assert len(kinds) == 4  # still only capex/npv/opex/payback


def test_as_dict(store: KuzuGraphStore) -> None:
    d = _by_kind(store, "capex").as_dict()
    assert set(d) == {"kind", "value", "unit", "note"}
    assert d == {
        "kind": "capex",
        "value": 5.0,
        "unit": "MUSD",
        "note": CAPEX_NOTE,
    }
