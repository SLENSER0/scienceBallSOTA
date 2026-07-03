"""Discrete 5-level graph proximity (§12.5 / §10.3).

Each test constructs one relationship tier over a temp KuzuGraphStore and
asserts the exact discrete level: self/direct=1.0, same-experiment=0.8,
same-material+property=0.6, same-document=0.4, same-community=0.2,
unrelated=0.0, plus the batch context and symmetry.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.proximity import (
    SCALE,
    ProximityScale,
    proximity_context,
    proximity_level,
)


def _build(s: KuzuGraphStore) -> None:
    # -- direct provenance edges (tier 1.0) --
    s.upsert_node("exp:1", "Experiment", name="эксперимент 1")
    s.upsert_node("meas:1", "Measurement", name="прочность", property_name="strength")
    s.upsert_node("ev:1", "Evidence", text="доказательство", doc_id="doc:src")
    s.upsert_edge("exp:1", "meas:1", "HAS_MEASUREMENT", confidence=1.0)
    s.upsert_edge("meas:1", "ev:1", "SUPPORTED_BY", confidence=1.0)

    # -- same Experiment (tier 0.8): shared experiment_id, differing material --
    s.upsert_node("se:a", "Measurement", experiment_id="exp:E1", material_id="m1", property_id="p1")
    s.upsert_node("se:b", "Measurement", experiment_id="exp:E1", material_id="m2", property_id="p2")

    # -- same Material AND Property (tier 0.6): no experiment, no shared doc --
    s.upsert_node("mp:a", "Measurement", material_id="m9", property_id="p9")
    s.upsert_node("mp:b", "Measurement", material_id="m9", property_id="p9")

    # -- same Material ONLY (property differs) -> must NOT reach 0.6 --
    s.upsert_node("mo:a", "Measurement", material_id="m5", property_id="pX")
    s.upsert_node("mo:b", "Measurement", material_id="m5", property_id="pY")

    # -- same Document (tier 0.4): shared doc, differing material, no experiment --
    s.upsert_node("dc:a", "Finding", doc_id="doc:D1", material_id="mA", property_id="pA")
    s.upsert_node("dc:b", "Finding", doc_id="doc:D1", material_id="mB", property_id="pB")

    # -- same community (tier 0.2): equal community_id, nothing else shared --
    s.upsert_node("cm:a", "Material", name="A", community_id=7)
    s.upsert_node("cm:b", "Material", name="B", community_id=7)

    # -- unrelated (tier 0.0): nothing shared --
    s.upsert_node("un:a", "Material", material_id="z1", doc_id="docZ1", community_id=1)
    s.upsert_node("un:b", "Material", material_id="z2", doc_id="docZ2", community_id=2)

    # -- batch seed carrying every membership key at once (§12.5 full scale) --
    s.upsert_node(
        "seed",
        "Measurement",
        experiment_id="exp:B",
        material_id="mb",
        property_id="pb",
        doc_id="doc:B",
        community_id=99,
    )
    s.upsert_node("c_exp", "Measurement", experiment_id="exp:B")
    s.upsert_node("c_mp", "Measurement", material_id="mb", property_id="pb")
    s.upsert_node("c_doc", "Finding", doc_id="doc:B", material_id="other", property_id="q")
    s.upsert_node("c_com", "Material", community_id=99)
    s.upsert_node("c_none", "Material", material_id="zzz")


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


def test_self_is_direct(store: KuzuGraphStore) -> None:
    assert proximity_level(store, "meas:1", "meas:1") == 1.0


def test_supported_by_is_direct(store: KuzuGraphStore) -> None:
    # meas:1 -SUPPORTED_BY-> ev:1
    assert proximity_level(store, "meas:1", "ev:1") == 1.0


def test_has_measurement_is_direct(store: KuzuGraphStore) -> None:
    # exp:1 -HAS_MEASUREMENT-> meas:1
    assert proximity_level(store, "exp:1", "meas:1") == 1.0


def test_same_experiment_is_0_8(store: KuzuGraphStore) -> None:
    assert proximity_level(store, "se:a", "se:b") == 0.8


def test_same_material_and_property_is_0_6(store: KuzuGraphStore) -> None:
    assert proximity_level(store, "mp:a", "mp:b") == 0.6


def test_material_without_property_is_not_material_tier(store: KuzuGraphStore) -> None:
    # shared material but different property must fall through to 0.0
    assert proximity_level(store, "mo:a", "mo:b") == 0.0


def test_same_document_is_0_4(store: KuzuGraphStore) -> None:
    assert proximity_level(store, "dc:a", "dc:b") == 0.4


def test_same_community_is_0_2(store: KuzuGraphStore) -> None:
    assert proximity_level(store, "cm:a", "cm:b") == 0.2


def test_unrelated_is_0_0(store: KuzuGraphStore) -> None:
    assert proximity_level(store, "un:a", "un:b") == 0.0


def test_proximity_is_symmetric(store: KuzuGraphStore) -> None:
    pairs = [
        ("exp:1", "meas:1"),
        ("meas:1", "ev:1"),
        ("se:a", "se:b"),
        ("mp:a", "mp:b"),
        ("dc:a", "dc:b"),
        ("cm:a", "cm:b"),
        ("un:a", "un:b"),
    ]
    for x, y in pairs:
        assert proximity_level(store, x, y) == proximity_level(store, y, x)


def test_proximity_context_returns_level_per_candidate(store: KuzuGraphStore) -> None:
    cands = ["seed", "c_exp", "c_mp", "c_doc", "c_com", "c_none"]
    ctx = proximity_context(store, "seed", cands)
    assert ctx == {
        "seed": 1.0,  # self
        "c_exp": 0.8,  # same experiment
        "c_mp": 0.6,  # same material + property
        "c_doc": 0.4,  # same document
        "c_com": 0.2,  # same community
        "c_none": 0.0,  # unrelated
    }
    # exactly one level per candidate
    assert set(ctx) == set(cands)


def test_proximity_context_direct_edges(store: KuzuGraphStore) -> None:
    # seed on a directly-linked node: both HAS_MEASUREMENT and SUPPORTED_BY → 1.0
    ctx = proximity_context(store, "meas:1", ["exp:1", "ev:1", "un:a"])
    assert ctx == {"exp:1": 1.0, "ev:1": 1.0, "un:a": 0.0}


def test_scale_as_dict_is_exact() -> None:
    assert SCALE.as_dict() == {
        "direct": 1.0,
        "same_experiment": 0.8,
        "same_material_property": 0.6,
        "same_document": 0.4,
        "same_community": 0.2,
        "unrelated": 0.0,
    }
    assert ProximityScale().direct == 1.0
