"""Tests for §8.15 typed (per-relationship-type) node degree.

Each test builds a fresh temp store seeded with the small graph:

    meas:cd  -ABOUT_REGIME->  regime:ew
    regime:ew -APPLIES_TO->   material:ni
    meas:cd  -SUPPORTED_BY->  ev:1

Hand-checked roles:

- ``meas:cd``: out ABOUT_REGIME 1 + SUPPORTED_BY 1 -> total_out 2, total_in 0;
- ``regime:ew``: in ABOUT_REGIME 1, out APPLIES_TO 1;
- ``material:ni``: in APPLIES_TO 1 -> total_in 1, total_out 0;
- ``ev:1``: in SUPPORTED_BY 1.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.graph_typed_degree import (
    TypedDegree,
    typed_degree,
    typed_degree_all,
)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KuzuGraphStore]:
    """Fresh embedded store (schema created, no nodes yet)."""
    s = KuzuGraphStore(str(tmp_path / "g"))
    yield s
    s.close()


def _seed_small(s: KuzuGraphStore) -> None:
    """Three-edge graph over four nodes (see module docstring)."""
    s.upsert_node("material:ni", "Material", name="Никель")
    s.upsert_node("regime:ew", "ProcessingRegime", name="electrowinning 60C")
    s.upsert_node("meas:cd", "Measurement", name="current density")
    s.upsert_node("ev:1", "Evidence", text="плотность тока 250 А/м²")
    s.upsert_edge("meas:cd", "regime:ew", "ABOUT_REGIME", confidence=0.9)
    s.upsert_edge("regime:ew", "material:ni", "APPLIES_TO", confidence=0.8)
    s.upsert_edge("meas:cd", "ev:1", "SUPPORTED_BY", confidence=1.0)


def test_source_node_out_by_type(store: KuzuGraphStore) -> None:
    _seed_small(store)
    td = typed_degree(store, "meas:cd")
    assert td.out_by_type == {"ABOUT_REGIME": 1, "SUPPORTED_BY": 1}
    assert td.total_out == 2
    assert td.total_in == 0
    assert td.in_by_type == {}


def test_middle_node_in_and_out(store: KuzuGraphStore) -> None:
    _seed_small(store)
    td = typed_degree(store, "regime:ew")
    assert td.in_by_type == {"ABOUT_REGIME": 1}
    assert td.out_by_type == {"APPLIES_TO": 1}
    assert td.total_in == 1
    assert td.total_out == 1


def test_sink_node_in_only(store: KuzuGraphStore) -> None:
    _seed_small(store)
    td = typed_degree(store, "material:ni")
    assert td.total_in == 1
    assert td.total_out == 0
    assert td.in_by_type == {"APPLIES_TO": 1}
    assert td.out_by_type == {}


def test_evidence_node_supported_by(store: KuzuGraphStore) -> None:
    _seed_small(store)
    td = typed_degree(store, "ev:1")
    assert td.in_by_type == {"SUPPORTED_BY": 1}
    assert td.total_in == 1
    assert td.total_out == 0


def test_unknown_node_is_empty(store: KuzuGraphStore) -> None:
    _seed_small(store)
    td = typed_degree(store, "unknown")
    assert td.out_by_type == {}
    assert td.in_by_type == {}
    assert td.total_out == 0
    assert td.total_in == 0
    assert td.node_id == "unknown"


def test_unknown_node_on_empty_store(store: KuzuGraphStore) -> None:
    td = typed_degree(store, "nope")
    assert td.total_out == 0
    assert td.total_in == 0


def test_all_has_key_for_every_incident_node(store: KuzuGraphStore) -> None:
    _seed_small(store)
    all_td = typed_degree_all(store)
    # All four nodes here are incident to at least one edge.
    assert set(all_td) == {"material:ni", "regime:ew", "meas:cd", "ev:1"}
    assert all_td["meas:cd"].total_out == 2
    assert all_td["material:ni"].total_in == 1


def test_all_excludes_isolated_node(store: KuzuGraphStore) -> None:
    _seed_small(store)
    store.upsert_node("iso", "Material", name="одиночка")
    all_td = typed_degree_all(store)
    assert "iso" not in all_td  # no incident edge -> absent
    # but an individual query still returns an empty fingerprint
    assert typed_degree(store, "iso").total_out == 0


def test_all_matches_individual(store: KuzuGraphStore) -> None:
    _seed_small(store)
    all_td = typed_degree_all(store)
    for nid in ("meas:cd", "regime:ew", "material:ni", "ev:1"):
        assert all_td[nid].as_dict() == typed_degree(store, nid).as_dict()


def test_as_dict_out_by_type_is_plain_dict(store: KuzuGraphStore) -> None:
    _seed_small(store)
    d = typed_degree(store, "meas:cd").as_dict()
    assert type(d["out_by_type"]) is dict
    assert d["out_by_type"] == {"ABOUT_REGIME": 1, "SUPPORTED_BY": 1}
    assert d["in_by_type"] == {}
    assert d["total_out"] == 2
    assert d["total_in"] == 0
    assert d["node_id"] == "meas:cd"


def test_typed_degree_is_frozen(store: KuzuGraphStore) -> None:
    td = typed_degree(store, "meas:cd")
    with pytest.raises(FrozenInstanceError):
        td.total_out = 99  # type: ignore[misc]


def test_typed_degree_dataclass_fields() -> None:
    td = TypedDegree("x", {"R": 2}, {}, 2, 0)
    assert td.as_dict() == {
        "node_id": "x",
        "out_by_type": {"R": 2},
        "in_by_type": {},
        "total_out": 2,
        "total_in": 0,
    }
