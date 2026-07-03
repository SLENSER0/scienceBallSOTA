"""GraphRAG global-vs-local routing + citation merge (§11.8).

Builds a small, fully deterministic two-community store by hand (no networkx, no
seed graph) so every expected community id, source document (документ) and Evidence
id (эвиденс) is hand-checkable:

- community 0 — water desalination: reverse osmosis, ion exchange, polyamide
  membrane; RO & ion-exchange cite ``water-2022.pdf`` / ``ev:water``;
- community 1 — steel metallurgy: stainless steel, austenitic alloy, electron
  microscopy; steel & alloy cite ``steel-2021.pdf`` / ``ev:steel``.
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.graphrag_orchestrator import (
    GraphRagResult,
    graphrag_answer,
    route_query,
)

_WATER_DOC = "water-2022.pdf"
_WATER_EV = "ev:water"
_STEEL_DOC = "steel-2021.pdf"
_STEEL_EV = "ev:steel"


def _build(store: KuzuGraphStore) -> None:
    """Two hand-wired communities with SUPPORTED_BY provenance + Finding summaries."""
    # -- community 0: water desalination ---------------------------------
    store.upsert_node(
        "e:ro",
        "TechnologySolution",
        name="reverse osmosis desalination",
        domain="water",
        aliases_text="membrane filtration",
        community_id=0,
    )
    store.upsert_node(
        "e:ie",
        "TechnologySolution",
        name="ion exchange",
        domain="water",
        aliases_text="resin softening",
        community_id=0,
    )
    store.upsert_node(
        "e:mem",
        "Material",
        name="polyamide membrane",
        domain="water",
        aliases_text="thin film",
        community_id=0,
    )
    store.upsert_node("ev:water", "Evidence", name="Water evidence", doc_id=_WATER_DOC)
    store.upsert_node(
        "f:0",
        "Finding",
        name="Community summary #0",
        community_id=0,
        text="Water desalination cluster: reverse osmosis and ion exchange membranes.",
    )
    # -- community 1: steel metallurgy -----------------------------------
    store.upsert_node(
        "e:steel",
        "Material",
        name="stainless steel",
        domain="metallurgy",
        aliases_text="corrosion resistant",
        community_id=1,
    )
    store.upsert_node(
        "e:alloy",
        "Alloy",
        name="austenitic alloy",
        domain="metallurgy",
        aliases_text="chromium nickel",
        community_id=1,
    )
    store.upsert_node(
        "e:micro",
        "Method",
        name="electron microscopy",
        domain="metallurgy",
        aliases_text="sem imaging",
        community_id=1,
    )
    store.upsert_node("ev:steel", "Evidence", name="Steel evidence", doc_id=_STEEL_DOC)
    store.upsert_node(
        "f:1",
        "Finding",
        name="Community summary #1",
        community_id=1,
        text="Steel metallurgy cluster: stainless steel and austenitic alloy.",
    )
    # -- provenance (SUPPORTED_BY) + intra-community RELATED edges --------
    for src, dst in (("e:ro", "ev:water"), ("e:ie", "ev:water")):
        store.upsert_edge(src, dst, "SUPPORTED_BY")
    for src, dst in (("e:steel", "ev:steel"), ("e:alloy", "ev:steel")):
        store.upsert_edge(src, dst, "SUPPORTED_BY")
    for src, dst in (("e:ro", "e:ie"), ("e:ro", "e:mem")):
        store.upsert_edge(src, dst, "RELATED")
    for src, dst in (("e:steel", "e:alloy"), ("e:steel", "e:micro")):
        store.upsert_edge(src, dst, "RELATED")


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


def test_broad_query_auto_routes_global_with_communities(store: KuzuGraphStore) -> None:
    res = graphrag_answer(store, "overview of water desalination methods")
    assert res.mode_used == "global"
    assert res.communities == [0]
    assert res.local_seeds == []
    # citations of the water community merged in
    assert res.doc_ids == [_WATER_DOC]
    assert res.evidence_ids == [_WATER_EV]


def test_entity_query_auto_routes_local_with_seeds(store: KuzuGraphStore) -> None:
    res = graphrag_answer(store, "reverse osmosis desalination")
    assert res.mode_used == "local"
    assert res.local_seeds == ["e:ro"]
    assert res.communities == [0]
    assert res.doc_ids == [_WATER_DOC]
    assert res.evidence_ids == [_WATER_EV]


def test_forced_global_on_entity_query(store: KuzuGraphStore) -> None:
    # an entity-shaped query, but mode overrides the heuristic to global
    res = graphrag_answer(store, "reverse osmosis", mode="global")
    assert res.mode_used == "global"
    assert res.communities == [0]
    assert res.local_seeds == []
    assert res.doc_ids == [_WATER_DOC]


def test_forced_local_traces_community_evidence(store: KuzuGraphStore) -> None:
    # seed (electron microscopy) carries no provenance itself, but its community does
    res = graphrag_answer(store, "electron microscopy", mode="local")
    assert res.mode_used == "local"
    assert res.local_seeds == ["e:micro"]
    assert res.communities == [1]
    assert res.doc_ids == [_STEEL_DOC]
    assert res.evidence_ids == [_STEEL_EV]


def test_route_query_heuristic(store: KuzuGraphStore) -> None:
    # thematic markers -> global; named specific entities -> local
    assert route_query(store, "overview of water desalination methods") == "global"
    assert route_query(store, "какие основные технологии") == "global"
    assert route_query(store, "reverse osmosis desalination") == "local"
    assert route_query(store, "stainless steel") == "local"
    # empty query is not entity-specific -> global (broad) fallback
    assert route_query(store, "") == "global"


def test_global_merges_and_dedups_across_communities(store: KuzuGraphStore) -> None:
    # "cluster" is a thematic marker AND appears in both community summaries
    res = graphrag_answer(store, "cluster")
    assert res.mode_used == "global"
    assert res.communities == [0, 1]
    # sorted, de-duplicated union of both communities' citations
    assert res.doc_ids == [_STEEL_DOC, _WATER_DOC]
    assert res.evidence_ids == [_STEEL_EV, _WATER_EV]
    assert len(res.doc_ids) == len(set(res.doc_ids))
    assert len(res.evidence_ids) == len(set(res.evidence_ids))


def test_empty_store_is_graceful() -> None:
    d = tempfile.mkdtemp()
    empty = KuzuGraphStore(str(Path(d) / "empty"))
    try:
        auto = graphrag_answer(empty, "reverse osmosis desalination")
        assert auto.mode_used == "global"
        assert auto.communities == [] and auto.doc_ids == [] and auto.evidence_ids == []
        forced = graphrag_answer(empty, "reverse osmosis", mode="local")
        assert forced.mode_used == "local"
        assert forced.local_seeds == [] and forced.doc_ids == []
    finally:
        empty.close()


def test_empty_query_is_graceful(store: KuzuGraphStore) -> None:
    res = graphrag_answer(store, "   ")
    assert res.mode_used == "global"
    assert res.communities == []
    assert res.doc_ids == []
    assert res.evidence_ids == []


def test_invalid_mode_raises(store: KuzuGraphStore) -> None:
    with pytest.raises(ValueError, match="mode must be one of"):
        graphrag_answer(store, "reverse osmosis", mode="hybrid")


def test_as_dict_shape_and_immutability(store: KuzuGraphStore) -> None:
    res = graphrag_answer(store, "reverse osmosis desalination")
    assert isinstance(res, GraphRagResult)
    d = res.as_dict()
    assert set(d) == {"mode_used", "communities", "local_seeds", "doc_ids", "evidence_ids"}
    assert d["mode_used"] == "local"
    assert d["local_seeds"] == ["e:ro"]
    assert d["doc_ids"] == [_WATER_DOC]
    assert d["evidence_ids"] == [_WATER_EV]
    # returned lists are copies — mutating them must not corrupt the frozen record
    d["doc_ids"].append("tampered")
    assert "tampered" not in res.doc_ids
    # frozen dataclass: attributes cannot be reassigned
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.mode_used = "global"  # type: ignore[misc]
