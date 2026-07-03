"""MENTIONS-lineage tracing over a hand-built graph (§25.7).

Builds a tiny corpus without relying on the seed (which carries no MENTIONS edges):

    Document(doc1)-HAS_CHUNK->Chunk(c1)-MENTIONS->{nickel, copper}
    Document(doc2)-HAS_CHUNK->Chunk(c2)-MENTIONS->{nickel}
    Measurement(recovery) -ABOUT_MATERIAL-> nickel   (an observation of 'recovery')

Hand-checked expectations:
- nickel is mentioned by doc1 + doc2; copper only by doc1;
- doc1 mentions {copper, nickel}; doc2 mentions {nickel};
- nickel has an observation of 'recovery' but none of 'conductivity'.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.mentions_lineage import (
    MentionLineage,
    documents_mentioning,
    entities_mentioned_in,
    is_mentioned_without_observation,
    mention_matrix,
)

DOC1 = make_id("Document", "doc one")
DOC2 = make_id("Document", "doc two")
C1 = make_id("Chunk", "chunk one")
C2 = make_id("Chunk", "chunk two")
NICKEL = make_id("Material", "nickel")
COPPER = make_id("Material", "copper")
PROP_RECOVERY = make_id("Property", "recovery")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build_corpus(s)
    yield s
    s.close()


def _build_corpus(s: KuzuGraphStore) -> None:
    """Two documents mentioning materials + one 'recovery' measurement on nickel."""
    s.upsert_node(DOC1, "Document", name="Doc One")
    s.upsert_node(DOC2, "Document", name="Doc Two")
    s.upsert_node(C1, "Chunk", text="nickel and copper leaching")
    s.upsert_node(C2, "Chunk", text="nickel electrowinning")
    s.upsert_node(NICKEL, "Material", name="nickel", domain="hydrometallurgy")
    s.upsert_node(COPPER, "Material", name="copper", domain="hydrometallurgy")
    s.upsert_node(PROP_RECOVERY, "Property", property_name="recovery", name="Recovery")

    meas = make_id("Measurement", "nickel recovery")
    s.upsert_node(meas, "Measurement", property_name="recovery", value_normalized=92.0)

    s.upsert_edge(DOC1, C1, "HAS_CHUNK")
    s.upsert_edge(DOC2, C2, "HAS_CHUNK")
    s.upsert_edge(C1, NICKEL, "MENTIONS")
    s.upsert_edge(C1, COPPER, "MENTIONS")
    s.upsert_edge(C2, NICKEL, "MENTIONS")
    s.upsert_edge(meas, NICKEL, "ABOUT_MATERIAL", confidence=0.9)


# -- forward trace ---------------------------------------------------------
def test_documents_mentioning_finds_docs(store: KuzuGraphStore) -> None:
    assert documents_mentioning(store, NICKEL) == [DOC1, DOC2]  # sorted, distinct
    assert documents_mentioning(store, COPPER) == [DOC1]


# -- reverse trace ---------------------------------------------------------
def test_entities_mentioned_in_reverse(store: KuzuGraphStore) -> None:
    # doc1's single chunk names both materials; doc2's names only nickel.
    assert entities_mentioned_in(store, DOC1) == sorted([COPPER, NICKEL])
    assert entities_mentioned_in(store, DOC2) == [NICKEL]


# -- aggregate matrix ------------------------------------------------------
def test_mention_matrix_aggregates(store: KuzuGraphStore) -> None:
    m = mention_matrix(store, [NICKEL, COPPER])
    assert isinstance(m, MentionLineage)
    assert m.by_entity == {NICKEL: [DOC1, DOC2], COPPER: [DOC1]}
    assert m.n_mentions == 3  # (nickel,doc1)+(nickel,doc2)+(copper,doc1)

    d = m.as_dict()
    assert set(d) == {"by_entity", "n_mentions"}
    assert d["by_entity"][NICKEL] == [DOC1, DOC2]
    assert d["n_mentions"] == 3


# -- possible_miss signal (§25.11) -----------------------------------------
def test_mentioned_without_observation_true_when_no_measurement(store: KuzuGraphStore) -> None:
    # nickel is mentioned, but there is no Measurement of 'conductivity' anywhere.
    assert is_mentioned_without_observation(store, NICKEL, "conductivity") is True


def test_mentioned_without_observation_false_when_measurement_present(
    store: KuzuGraphStore,
) -> None:
    # nickel is mentioned AND has a 'recovery' measurement → not a possible_miss.
    # property_id given as a Property node id, resolved to property_name='recovery'.
    assert is_mentioned_without_observation(store, NICKEL, PROP_RECOVERY) is False
    # copper is mentioned but has no measurement of 'recovery' → possible_miss.
    assert is_mentioned_without_observation(store, COPPER, PROP_RECOVERY) is True


# -- graceful edge cases ---------------------------------------------------
def test_unknown_ids_graceful(store: KuzuGraphStore) -> None:
    assert documents_mentioning(store, "material:does-not-exist") == []
    assert entities_mentioned_in(store, "document:does-not-exist") == []
    # a material that is never mentioned is never a possible_miss (False, not error).
    assert is_mentioned_without_observation(store, "material:ghost", "recovery") is False


def test_empty_matrix(store: KuzuGraphStore) -> None:
    m = mention_matrix(store, [])
    assert m.by_entity == {}
    assert m.n_mentions == 0
    assert m.as_dict() == {"by_entity": {}, "n_mentions": 0}
