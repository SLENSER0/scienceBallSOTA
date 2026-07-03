"""Observed edge-schema profiler over a temp Kuzu store (§8.2).

Hand-built graph:
- ``Evidence-[:SUPPORTS]->Claim``  twice (e1->c1, e2->c1) -> one triple, count 2,
  declared True (matches EDGE_SCHEMA signature Evidence SUPPORTS Claim);
- ``Chunk-[:MENTIONS]->Material``  once -> declared True via Entity expansion
  (Chunk MENTIONS Entity; Material is an ENTITY_LABEL);
- ``Material-[:MEASURED]->Person``  once -> undeclared (no such signature).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.observed_schema_profile import (
    ObservedSchemaProfile,
    ObservedTriple,
    profile_observed_schema,
)


def _build(store: KuzuGraphStore) -> None:
    store.upsert_node("e1", "Evidence", name="ev 1")
    store.upsert_node("e2", "Evidence", name="ev 2")
    store.upsert_node("c1", "Claim", name="claim 1")
    store.upsert_node("ch1", "Chunk", name="chunk 1")
    store.upsert_node("m1", "Material", name="steel")
    store.upsert_node("p1", "Person", name="ivan")
    # two collapsing SUPPORTS edges
    store.upsert_edge("e1", "c1", "SUPPORTS")
    store.upsert_edge("e2", "c1", "SUPPORTS")
    # declared via Entity expansion
    store.upsert_edge("ch1", "m1", "MENTIONS")
    # injected undeclared triple
    store.upsert_edge("m1", "p1", "MEASURED")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _find(profile: ObservedSchemaProfile, f: str, r: str, t: str) -> ObservedTriple:
    for tr in profile.triples:
        if (tr.from_label, tr.rel_type, tr.to_label) == (f, r, t):
            return tr
    raise AssertionError(f"triple {f}-{r}-{t} not found")


def test_supports_collapses_to_count_two(store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(store)
    tr = _find(profile, "Evidence", "SUPPORTS", "Claim")
    assert tr.count == 2
    assert tr.declared is True


def test_injected_triple_undeclared(store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(store)
    tr = _find(profile, "Material", "MEASURED", "Person")
    assert tr.declared is False
    assert tr in profile.undeclared


def test_distinct_rel_types(store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(store)
    assert profile.distinct_rel_types == frozenset({"SUPPORTS", "MENTIONS", "MEASURED"})


def test_fully_declared_false_when_undeclared_present(store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(store)
    assert profile.undeclared  # non-empty
    assert profile.fully_declared is False


def test_highest_count_first(store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(store)
    # SUPPORTS (count 2) is the unique max; the rest are count 1
    assert profile.triples[0].count == 2
    assert (
        profile.triples[0].from_label,
        profile.triples[0].rel_type,
        profile.triples[0].to_label,
    ) == ("Evidence", "SUPPORTS", "Claim")
    assert profile.triples[0].count >= profile.triples[-1].count


def test_chunk_mentions_material_declared_via_entity(store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(store)
    tr = _find(profile, "Chunk", "MENTIONS", "Material")
    assert tr.declared is True


def test_empty_store(empty_store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(empty_store)
    assert profile.triples == ()
    assert profile.undeclared == ()
    assert profile.distinct_rel_types == frozenset()
    assert profile.fully_declared is True


def test_as_dict_undeclared_is_list_of_dicts(store: KuzuGraphStore) -> None:
    d = profile_observed_schema(store).as_dict()
    assert isinstance(d["undeclared"], list)
    assert all(isinstance(item, dict) for item in d["undeclared"])
    assert {
        "from_label": "Material",
        "rel_type": "MEASURED",
        "to_label": "Person",
        "count": 1,
        "declared": False,
    } in d["undeclared"]


def test_triples_sorted_count_desc_then_lex(store: KuzuGraphStore) -> None:
    profile = profile_observed_schema(store)
    keys = [(-t.count, t.from_label, t.rel_type, t.to_label) for t in profile.triples]
    assert keys == sorted(keys)


def test_fully_declared_true_when_all_declared(empty_store: KuzuGraphStore) -> None:
    empty_store.upsert_node("e1", "Evidence", name="ev")
    empty_store.upsert_node("c1", "Claim", name="claim")
    empty_store.upsert_edge("e1", "c1", "SUPPORTS")
    profile = profile_observed_schema(empty_store)
    assert profile.undeclared == ()
    assert profile.fully_declared is True
