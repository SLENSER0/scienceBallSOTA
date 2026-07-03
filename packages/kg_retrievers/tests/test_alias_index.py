"""In-memory alias / fulltext entity index (§3.12 aliases_text, §8.4 entity_name_index).

Hand-checkable tests over the deterministic seed graph (§3.17): the reverse-osmosis
(обратный осмос) TechnologySolution is the anchor entity because its aliases are unique
in the corpus, so exact/fuzzy/token-overlap all have a single unambiguous target.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_common import make_id
from kg_retrievers.alias_index import AliasIndex
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

# Unique-alias anchors from the seed (§3.17).
RO = make_id("TechnologySolution", "reverse osmosis desalination")  # обратный осмос
WATER = make_id("Material", "mine water concentrator feed")  # mine water


def _seeded_index() -> AliasIndex:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    idx = AliasIndex.build_from_store(store)
    store.close()
    return idx


def test_build_indexes_entities() -> None:
    idx = _seeded_index()
    # The seed has many entity-labelled nodes with names/aliases.
    assert len(idx) > 0
    assert idx.n_aliases > 0
    # The RO entity was captured with its folded surface forms.
    entry = idx.entry(RO)
    assert entry is not None
    assert entry.label == "TechnologySolution"
    assert "обратный осмос" in entry.aliases
    assert entry.as_dict()["entity_id"] == RO


def test_lookup_exact_ru_alias() -> None:
    idx = _seeded_index()
    # §3.12: 'обратный осмос' is a pipe-separated alias of the RO solution.
    assert idx.lookup_exact("обратный осмос") == RO


def test_lookup_exact_case_insensitive() -> None:
    idx = _seeded_index()
    # RU/EN case-folding: upper- and mixed-case surfaces fold to the same key.
    assert idx.lookup_exact("ОБРАТНЫЙ ОСМОС") == RO
    assert idx.lookup_exact("Reverse Osmosis") == RO


def test_lookup_exact_unknown_is_none() -> None:
    idx = _seeded_index()
    assert idx.lookup_exact("квантовая криптография") is None
    assert idx.lookup_exact("   ") is None


def test_search_ranked_ids() -> None:
    idx = _seeded_index()
    # 'осмос' occurs only in the RO entity -> it is the sole, top-ranked hit at 1.0.
    hits = idx.search("обратный осмос")
    assert hits
    ids = [eid for eid, _ in hits]
    assert ids[0] == RO
    scores = [score for _, score in hits]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 1.0


def test_search_multi_token_query() -> None:
    idx = _seeded_index()
    # Multi-token 'mine water' fully overlaps only the mine-water Material (score 1.0).
    hits = idx.search("mine water")
    assert hits and hits[0][0] == WATER
    assert hits[0][1] == 1.0
    # A single-token query still returns that entity, but at a lower overlap score.
    partial = dict(idx.search("water"))
    assert WATER in partial


def test_resolve_exact_then_id() -> None:
    idx = _seeded_index()
    # Exact path wins before any fuzzy work is done.
    assert idx.resolve("обратный осмос") == RO


def test_resolve_fuzzy_near_miss() -> None:
    idx = _seeded_index()
    # Russian склонение 'обратного осмоса' is not an exact key, but token_set_ratio
    # (~80) clears the threshold and still grounds onto the RO solution (§8.4).
    assert idx.lookup_exact("обратного осмоса") is None
    assert idx.resolve("обратного осмоса") == RO


def test_resolve_unknown_is_none() -> None:
    idx = _seeded_index()
    # No exact key and every fuzzy candidate scores below RESOLVE_MIN_SCORE.
    assert idx.resolve("квантовая криптография") is None
    assert idx.resolve("") is None
