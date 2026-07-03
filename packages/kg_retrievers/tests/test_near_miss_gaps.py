"""Near-miss gap enumeration over a hand-built MENTIONS graph (§25.8).

Builds a tiny corpus (no seed dependency — the seed carries no MENTIONS edges):

    Document(d1)-HAS_CHUNK->Chunk(c1)-MENTIONS->m1
    Measurement(yield_strength) -ABOUT_MATERIAL-> m1   (an observation)
    m2 exists but is mentioned by no document.

Hand-checked expectations over the grid materials={m1, m2},
properties={hardness, yield_strength}:
- m1 is mentioned by d1 and has a 'yield_strength' measurement but no 'hardness';
- (m1,'hardness')     -> near-miss candidate, doc_ids=['d1'], has_observation=False;
- (m1,'yield_strength') -> NOT a candidate (observation exists);
- m2 is mentioned by no document -> contributes no candidate.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.near_miss_gaps import (
    NearMissCandidate,
    NearMissReport,
    find_near_miss_gaps,
)

D1 = make_id("Document", "doc one")
C1 = make_id("Chunk", "chunk one")
M1 = make_id("Material", "m one")
M2 = make_id("Material", "m two")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build_corpus(s)
    yield s
    s.close()


def _build_corpus(s: KuzuGraphStore) -> None:
    """d1 mentions m1; m1 has a 'yield_strength' measurement but no 'hardness'."""
    s.upsert_node(D1, "Document", name="Doc One")
    s.upsert_node(C1, "Chunk", text="m1 tensile testing")
    s.upsert_node(M1, "Material", name="m1", domain="metallurgy")
    s.upsert_node(M2, "Material", name="m2", domain="metallurgy")

    meas = make_id("Measurement", "m1 yield")
    s.upsert_node(meas, "Measurement", property_name="yield_strength", value_normalized=250.0)

    s.upsert_edge(D1, C1, "HAS_CHUNK")
    s.upsert_edge(C1, M1, "MENTIONS")
    s.upsert_edge(meas, M1, "ABOUT_MATERIAL", confidence=0.9)


def test_hardness_is_a_candidate(store: KuzuGraphStore) -> None:
    # m1 is mentioned by d1 and has NO 'hardness' observation → near-miss.
    report = find_near_miss_gaps(store, [M1], ["hardness", "yield_strength"])
    names = {(c.material_id, c.property_name) for c in report.candidates}
    assert (M1, "hardness") in names
    cand = next(c for c in report.candidates if c.property_name == "hardness")
    assert cand.doc_ids == [D1]
    assert cand.has_observation is False


def test_observed_property_is_not_a_candidate(store: KuzuGraphStore) -> None:
    # m1 HAS a 'yield_strength' measurement → NOT a near-miss.
    report = find_near_miss_gaps(store, [M1], ["hardness", "yield_strength"])
    names = {(c.material_id, c.property_name) for c in report.candidates}
    assert (M1, "yield_strength") not in names
    # exactly one candidate: (m1, hardness).
    assert report.candidates == [NearMissCandidate(M1, "hardness", [D1], False)]


def test_unmentioned_material_yields_no_candidate(store: KuzuGraphStore) -> None:
    # m2 is mentioned by no document → contributes nothing, even for a missing prop.
    report = find_near_miss_gaps(store, [M2], ["hardness", "yield_strength"])
    assert report.candidates == []
    assert report.n_candidates == 0


def test_n_candidates_and_sorting(store: KuzuGraphStore) -> None:
    # Over the full grid only (m1, hardness) survives; m2 drops out entirely.
    report = find_near_miss_gaps(store, [M1, M2], ["yield_strength", "hardness"])
    assert isinstance(report, NearMissReport)
    assert report.n_candidates == len(report.candidates) == 1
    # sorted by (material_id, property_name) even though input props were reversed.
    ordered = [(c.material_id, c.property_name) for c in report.candidates]
    assert ordered == sorted(ordered)
    assert ordered == [(M1, "hardness")]


def test_as_dict_is_plain_dicts(store: KuzuGraphStore) -> None:
    report = find_near_miss_gaps(store, [M1], ["hardness"])
    d = report.as_dict()
    assert set(d) == {"candidates", "n_candidates"}
    assert d["n_candidates"] == 1
    assert isinstance(d["candidates"], list)
    assert all(isinstance(c, dict) for c in d["candidates"])
    assert d["candidates"][0] == {
        "material_id": M1,
        "property_name": "hardness",
        "doc_ids": [D1],
        "has_observation": False,
    }
