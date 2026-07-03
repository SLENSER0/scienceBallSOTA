"""Tests for §24.25 per-domain summary over a KuzuGraphStore.

Each test builds a fresh temp store and asserts concrete, hand-checked values.

Hand-checkable seed (see ``_seed``), domain ``water_treatment``:
- solutions: sol:1 (TechnologySolution) + sol:2 (Method) = 2;
- measurements: meas:1, meas:2, meas:3 = 3;
- gaps: gap:1 = 1;
- materials (by incident-edge degree):
  * nickel = sol:1, sol:2, meas:1 -> degree 3;
  * copper = sol:1, meas:2 -> degree 2;
  * iron   = meas:3 -> degree 1.

Domain ``air_quality``:
- solutions: sol:3 (TechnologySolution) = 1;
- measurements: meas:4 = 1;
- gaps: none = 0;
- materials: carbon (no edges) -> degree 0.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kg_retrievers.domain_summary import DomainSummary, domain_summary
from kg_retrievers.graph_store import KuzuGraphStore

WATER = "water_treatment"
AIR = "air_quality"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KuzuGraphStore]:
    """Fresh embedded store (schema created, no nodes yet)."""
    s = KuzuGraphStore(str(tmp_path / "g"))
    yield s
    s.close()


def _seed(s: KuzuGraphStore) -> None:
    """Two domains with hand-checkable counts and material degrees (see docstring)."""
    # water_treatment core nodes
    s.upsert_node("sol:1", "TechnologySolution", name="Обратный осмос", domain=WATER)
    s.upsert_node("sol:2", "Method", name="Ионный обмен", domain=WATER)
    s.upsert_node("meas:1", "Measurement", property_name="tds", value_normalized=50.0, domain=WATER)
    s.upsert_node("meas:2", "Measurement", property_name="ph", value_normalized=7.0, domain=WATER)
    s.upsert_node("meas:3", "Measurement", property_name="cl", value_normalized=25.0, domain=WATER)
    s.upsert_node("gap:1", "Gap", gap_type="missing_measurement", domain=WATER)
    s.upsert_node("mat:1", "Material", name="Никель", canonical_name="nickel", domain=WATER)
    s.upsert_node("mat:2", "Material", name="Медь", canonical_name="copper", domain=WATER)
    s.upsert_node("mat:3", "Material", name="Железо", canonical_name="iron", domain=WATER)

    # air_quality core nodes
    s.upsert_node("sol:3", "TechnologySolution", name="Скруббер", domain=AIR)
    s.upsert_node("meas:4", "Measurement", property_name="pm25", value_normalized=35.0, domain=AIR)
    s.upsert_node("mat:4", "Material", name="Углерод", canonical_name="carbon", domain=AIR)

    # edges giving material degrees: nickel=3, copper=2, iron=1, carbon=0
    s.upsert_edge("sol:1", "mat:1", "USES_MATERIAL", confidence=0.9)
    s.upsert_edge("sol:2", "mat:1", "USES_MATERIAL", confidence=0.8)
    s.upsert_edge("meas:1", "mat:1", "ABOUT_MATERIAL", confidence=0.7)
    s.upsert_edge("sol:1", "mat:2", "USES_MATERIAL", confidence=0.6)
    s.upsert_edge("meas:2", "mat:2", "ABOUT_MATERIAL", confidence=0.5)
    s.upsert_edge("meas:3", "mat:3", "ABOUT_MATERIAL", confidence=0.4)


def test_counts_per_domain(store: KuzuGraphStore) -> None:
    _seed(store)
    summ = domain_summary(store, WATER)
    assert summ.domain == WATER
    assert summ.n_solutions == 2
    assert summ.n_measurements == 3
    assert summ.n_gaps == 1


def test_top_materials(store: KuzuGraphStore) -> None:
    _seed(store)
    summ = domain_summary(store, WATER)
    assert summ.top_materials == (("nickel", 3), ("copper", 2), ("iron", 1))


def test_unknown_domain_zeros(store: KuzuGraphStore) -> None:
    _seed(store)
    summ = domain_summary(store, "no_such_domain")
    assert summ.n_solutions == 0
    assert summ.n_measurements == 0
    assert summ.n_gaps == 0
    assert summ.top_materials == ()


def test_filter_isolates_domain(store: KuzuGraphStore) -> None:
    _seed(store)
    summ = domain_summary(store, AIR)
    assert summ.n_solutions == 1
    assert summ.n_measurements == 1
    assert summ.n_gaps == 0
    # carbon has no incident edges -> degree 0, still listed
    assert summ.top_materials == (("carbon", 0),)


def test_empty_store(store: KuzuGraphStore) -> None:
    summ = domain_summary(store, WATER)
    assert summ.n_solutions == 0
    assert summ.n_measurements == 0
    assert summ.n_gaps == 0
    assert summ.top_materials == ()


def test_top_k_cap(store: KuzuGraphStore) -> None:
    _seed(store)
    summ = domain_summary(store, WATER, top_k=2)
    assert summ.top_materials == (("nickel", 3), ("copper", 2))


def test_as_dict_and_frozen(store: KuzuGraphStore) -> None:
    _seed(store)
    summ = domain_summary(store, WATER)
    assert summ.as_dict() == {
        "domain": WATER,
        "n_solutions": 2,
        "n_measurements": 3,
        "n_gaps": 1,
        "top_materials": [
            {"material": "nickel", "degree": 3},
            {"material": "copper", "degree": 2},
            {"material": "iron", "degree": 1},
        ],
    }
    assert isinstance(summ, DomainSummary)
    with pytest.raises(FrozenInstanceError):
        summ.n_gaps = 99  # type: ignore[misc]
