"""Directed HITS hubs & authorities tests (§3.14 / §12.8).

Hand-checkable directed graph over a fresh temp Kuzu store. Two hubs point at a
single shared authority: ``x → z`` and ``y → z``. By Kleinberg's HITS:

- ``z`` is the sole authority (both edges terminate there);
- ``x`` and ``y`` are pure hubs (no incoming edges -> zero authority);
- ``z`` is a pure authority (no outgoing edges -> zero hub);
- each score set is normalised to sum 1.0.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_hits import (
    HitsScore,
    hits,
    top_authorities,
    top_hubs,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _node(store: KuzuGraphStore, nid: str) -> None:
    store.upsert_node(nid, "Material", name=nid)


def _hub_authority_store() -> KuzuGraphStore:
    store = _store()
    for nid in ("x", "y", "z"):
        _node(store, nid)
    store.upsert_edge("x", "z", "RELATED_TO")
    store.upsert_edge("y", "z", "RELATED_TO")
    return store


def test_all_three_entities_scored() -> None:
    store = _hub_authority_store()
    try:
        scored = hits(store)
        assert len(scored) == 3
        assert all(isinstance(s, HitsScore) for s in scored)
        assert {s.entity_id for s in scored} == {"x", "y", "z"}
    finally:
        store.close()


def test_z_is_the_top_authority() -> None:
    store = _hub_authority_store()
    try:
        top = top_authorities(store)
        assert top[0].entity_id == "z"
        z = next(s for s in top if s.entity_id == "z")
        x = next(s for s in top if s.entity_id == "x")
        # the shared target outranks its hubs on authority.
        assert z.authority > x.authority
    finally:
        store.close()


def test_pure_hub_and_pure_authority_scores() -> None:
    store = _hub_authority_store()
    try:
        scored = {s.entity_id: s for s in hits(store)}
        # x points outward -> positive hub; z only receives -> zero hub.
        assert scored["x"].hub > 0.0
        assert scored["z"].hub == pytest.approx(0.0)
    finally:
        store.close()


def test_authority_scores_sum_to_one() -> None:
    store = _hub_authority_store()
    try:
        total = sum(s.authority for s in hits(store))
        assert total == pytest.approx(1.0, abs=1e-6)
    finally:
        store.close()


def test_top_hub_is_one_of_the_sources() -> None:
    store = _hub_authority_store()
    try:
        top = top_hubs(store)
        assert top[0].entity_id in {"x", "y"}
        # ranked by hub, non-increasing.
        assert top == sorted(top, key=lambda s: (-s.hub, s.entity_id))
    finally:
        store.close()


def test_as_dict_shape() -> None:
    store = _hub_authority_store()
    try:
        z = next(s for s in hits(store) if s.entity_id == "z")
        assert z.as_dict() == {
            "entity_id": "z",
            "hub": z.hub,
            "authority": z.authority,
        }
    finally:
        store.close()


def test_empty_store_returns_empty() -> None:
    store = _store()
    try:
        assert hits(store) == []
        assert top_authorities(store) == []
        assert top_hubs(store) == []
    finally:
        store.close()
