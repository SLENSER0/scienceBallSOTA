"""Entity-level semantic index (§3.13 / §4.5 / §4.6). Loads the fastembed model."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.entity_index import EntityVectorIndex
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

NICKEL = make_id("Material", "nickel")
NI_ELEMENT = make_id("ChemicalElement", "Ni")
CATHOLYTE = make_id("Material", "catholyte nickel")
EW = make_id("TechnologySolution", "catholyte circulation scheme")
GAP = make_id("Gap", "cold heap leaching nickel gap")


def _seeded_store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    return store


@pytest.mark.slow
def test_index_entities_and_similar() -> None:
    store = _seeded_store()
    idx = EntityVectorIndex(collection="test_entities", on_disk=False)

    n = idx.index_entities(store)
    # Every resolvable :Entity node is embedded (materials, tech, elements, ...) and
    # only those — the count must match the graph's entity-label population exactly.
    from kg_schema.labels import ENTITY_LABELS

    expected = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels "
        "AND (n.name IS NOT NULL OR n.aliases_text IS NOT NULL) RETURN count(n)",
        {"labels": list(ENTITY_LABELS)},
    )[0][0]
    assert n == expected > 0
    assert idx.count() == n
    # Non-entity nodes (Gap/Measurement/Evidence) are excluded from the index: the
    # Gap id has no stored point, so it resolves via the free-text fallback and never
    # returns itself.
    assert GAP not in {h.id for h in idx.similar_entities(GAP, k=5)}

    hits = idx.similar_entities("nickel electrowinning", k=10)
    assert hits
    ids = {h.id for h in hits}
    # The nickel-electrowinning query grounds onto the catholyte/nickel entities.
    assert NICKEL in ids or NI_ELEMENT in ids
    assert CATHOLYTE in ids or EW in ids
    # Scores are similarities in descending order.
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.slow
def test_similar_by_entity_id_excludes_self() -> None:
    store = _seeded_store()
    idx = EntityVectorIndex(collection="test_entities_byid", on_disk=False)
    idx.index_entities(store)

    hits = idx.similar_entities(CATHOLYTE, k=5)
    ids = {h.id for h in hits}
    # Query-by-id must not return the query entity itself...
    assert CATHOLYTE not in ids
    # ...and the catholyte-circulation scheme is its nearest neighbour.
    assert EW in ids
