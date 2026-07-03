"""Expert / lab finder for a topic — «к кому обратиться» (§24.12).

Hand-checked against the seed graph (§3.17 / §24.2), whose expert corner is:

    Person(Иванов И.И.)  -MEMBER_OF->  Lab(Лаборатория гидрометаллургии)
    Person(Иванов И.И.)  -EXPERT_IN->  TechnologySolution(catholyte-circulation scheme)
    Lab(...)             -EXPERT_IN->  TechnologySolution(catholyte-circulation scheme)

The catholyte-circulation scheme carries ``domain='electrometallurgy'``. A few
tests add extra fixtures on top of the seeded store (never editing the seed) to
pin the ranking and to exercise the PERFORMED_BY / ResearchTeam path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.experts import ExpertHit, experts_for_domain, find_experts
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

EW = make_id("TechnologySolution", "catholyte circulation scheme")
PERSON = make_id("Person", "expert ivanov")
LAB = make_id("Lab", "hydrometallurgy lab")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(s)
    yield s
    s.close()


# -- core discovery --------------------------------------------------------
def test_find_experts_catholyte_returns_person_and_lab(store: KuzuGraphStore) -> None:
    hits = find_experts(store, [EW])
    ids = {h.id for h in hits}
    # Both the expert person and the lab are EXPERT_IN the catholyte scheme.
    assert ids == {PERSON, LAB}
    by_id = {h.id: h for h in hits}
    assert by_id[PERSON].name == "Иванов И.И."
    assert by_id[LAB].name == "Лаборатория гидрометаллургии"
    # Each connects to exactly the one queried topic → score 1, topics == [EW].
    assert by_id[PERSON].score == 1
    assert by_id[PERSON].topics == (EW,)


# -- ranking by connection count ------------------------------------------
def test_ranked_by_score_desc(store: KuzuGraphStore) -> None:
    # Give the person a second topic so they out-connect the lab (2 vs 1).
    topic2 = make_id("TechnologySolution", "test extra scheme")
    store.upsert_node(topic2, "TechnologySolution", name="extra scheme")
    store.upsert_edge(PERSON, topic2, "EXPERT_IN", confidence=0.5)

    hits = find_experts(store, [EW, topic2])
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)  # ranked by score desc
    assert hits[0].id == PERSON  # 2 connections beats the lab's 1
    assert hits[0].score == 2
    assert hits[1].id == LAB
    assert hits[1].score == 1


# -- domain roll-up --------------------------------------------------------
def test_experts_for_domain_electrometallurgy(store: KuzuGraphStore) -> None:
    hits = experts_for_domain(store, "electrometallurgy")
    ids = {h.id for h in hits}
    # The catholyte scheme is electrometallurgy; both experts surface via it.
    assert len(hits) >= 1
    assert PERSON in ids
    assert LAB in ids


# -- graceful empties ------------------------------------------------------
def test_unknown_topic_returns_empty(store: KuzuGraphStore) -> None:
    assert find_experts(store, ["tech:does-not-exist"]) == []
    assert find_experts(store, []) == []
    assert experts_for_domain(store, "no-such-domain") == []
    assert experts_for_domain(store, "") == []


# -- type field ------------------------------------------------------------
def test_type_field_is_node_label(store: KuzuGraphStore) -> None:
    by_id = {h.id: h for h in find_experts(store, [EW])}
    assert by_id[PERSON].type == "Person"
    assert by_id[LAB].type == "Lab"


def test_performed_by_and_research_team(store: KuzuGraphStore) -> None:
    # PERFORMED_BY runs topic→expert; the undirected match must still catch it,
    # and ResearchTeam is a valid expert label.
    team = make_id("ResearchTeam", "test team")
    store.upsert_node(team, "ResearchTeam", name="Команда исследователей")
    store.upsert_edge(EW, team, "PERFORMED_BY", confidence=0.7)

    hits = find_experts(store, [EW])
    by_id = {h.id: h for h in hits}
    assert team in by_id
    assert by_id[team].type == "ResearchTeam"
    assert by_id[team].topics == (EW,)


# -- serialisation shape ---------------------------------------------------
def test_as_dict_shape(store: KuzuGraphStore) -> None:
    hit = next(h for h in find_experts(store, [EW]) if h.id == PERSON)
    assert isinstance(hit, ExpertHit)
    d = hit.as_dict()
    assert set(d) == {"id", "type", "name", "score", "topics"}
    assert d["id"] == PERSON
    assert d["type"] == "Person"
    assert d["name"] == "Иванов И.И."
    assert isinstance(d["topics"], list)
    assert d["topics"] == [EW]
    # score is the connection count == number of distinct topics.
    assert d["score"] == len(d["topics"]) == 1


# -- limit -----------------------------------------------------------------
def test_limit_caps_results(store: KuzuGraphStore) -> None:
    assert len(find_experts(store, [EW])) == 2
    assert len(find_experts(store, [EW], limit=1)) == 1
