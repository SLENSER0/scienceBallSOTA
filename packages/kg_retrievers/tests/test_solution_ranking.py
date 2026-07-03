"""Technology-solution ranking over a temp graph (§24.21).

Hand-built store (no seed), scored against the §24.21 formula::

    score = 1.0*evidence_count + 2.0*verified_count + 1.0*recency
    recency(year) = clamp((year - 2000) / 25, 0, 1)   # most recent year wins

Four solutions, all values checkable by hand:

- A ``tech:sol-a`` (water_treatment, year 2025): 3 evidence (1 verified) + a non-evidence
  ``Gap`` link that must be ignored -> score 1*3 + 2*1 + 1*1.0 = 6.0
- B ``tech:sol-b`` (water_treatment, year 2020): 2 evidence, both verified (flag + level)
  -> score 1*2 + 2*2 + 1*0.8 = 6.8
- C ``tech:sol-c`` (air_quality, year 2010): 1 evidence, none verified
  -> score 1*1 + 0 + 1*0.4 = 1.4
- D ``tech:sol-d`` (water_treatment, no year, no evidence) -> score 0.0
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.solution_ranking import RankedSolution, rank_solutions

SOL_A = "tech:sol-a"
SOL_B = "tech:sol-b"
SOL_C = "tech:sol-c"
SOL_D = "tech:sol-d"


def _new_store() -> KuzuGraphStore:
    return KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    s = _new_store()
    # A: 3 evidence (1 verified) + one non-evidence Gap link (must not count)
    s.upsert_node(
        SOL_A,
        "TechnologySolution",
        name="Solution A (решение А)",
        domain="water_treatment",
        year=2025,
    )
    s.upsert_node("ev-a1", "Evidence", verified=True)
    s.upsert_node("ev-a2", "Evidence", verified=False)
    s.upsert_node("pa-a", "Paper")
    s.upsert_node("gap-a", "Gap", name="not evidence")
    for dst in ("ev-a1", "ev-a2", "pa-a", "gap-a"):
        s.upsert_edge(SOL_A, dst, "HAS_EVIDENCE", confidence=0.9)

    # B: 2 evidence, both verified — one via the flag, one via verification_level
    s.upsert_node(
        SOL_B,
        "TechnologySolution",
        name="Solution B (решение Б)",
        domain="water_treatment",
        year=2020,
    )
    s.upsert_node("ev-b1", "Evidence", verified=True)
    s.upsert_node("m-b1", "Measurement", verification_level="verified")
    s.upsert_edge(SOL_B, "ev-b1", "HAS_EVIDENCE")
    s.upsert_edge(SOL_B, "m-b1", "HAS_EVIDENCE")

    # C: 1 evidence, unverified, different domain
    s.upsert_node(SOL_C, "TechnologySolution", name="Solution C", domain="air_quality", year=2010)
    s.upsert_node("ev-c1", "Evidence", verified=False)
    s.upsert_edge(SOL_C, "ev-c1", "HAS_EVIDENCE")

    # D: no evidence, no year (recency 0.0), no explicit name
    s.upsert_node(SOL_D, "TechnologySolution", domain="water_treatment")

    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    s = _new_store()
    yield s
    s.close()


def _by_id(ranked: list[RankedSolution]) -> dict[str, RankedSolution]:
    return {r.solution_id: r for r in ranked}


def test_ranked_desc_by_score(store: KuzuGraphStore) -> None:
    ranked = rank_solutions(store)
    # every solution is present, ordered strictly by descending score
    assert [r.solution_id for r in ranked] == [SOL_B, SOL_A, SOL_C, SOL_D]
    assert [r.score for r in ranked] == pytest.approx([6.8, 6.0, 1.4, 0.0])
    # scores are monotonically non-increasing
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_evidence_count_counted(store: KuzuGraphStore) -> None:
    ranked = _by_id(rank_solutions(store))
    # A links four nodes but the Gap is not evidence -> only 3 counted
    assert ranked[SOL_A].evidence_count == 3
    assert ranked[SOL_B].evidence_count == 2
    assert ranked[SOL_C].evidence_count == 1
    assert ranked[SOL_D].evidence_count == 0


def test_verified_count(store: KuzuGraphStore) -> None:
    ranked = _by_id(rank_solutions(store))
    # A: one verified (flag True) of three
    assert ranked[SOL_A].verified_count == 1
    # B: both verified — ev-b1 via flag, m-b1 via verification_level='verified'
    assert ranked[SOL_B].verified_count == 2
    # C: unverified evidence only
    assert ranked[SOL_C].verified_count == 0


def test_domain_filter(store: KuzuGraphStore) -> None:
    ranked = rank_solutions(store, domain="water_treatment")
    # only the three water_treatment solutions survive; C (air_quality) is dropped
    assert [r.solution_id for r in ranked] == [SOL_B, SOL_A, SOL_D]
    assert SOL_C not in {r.solution_id for r in ranked}
    # scores are unchanged by scoping
    assert _by_id(ranked)[SOL_B].score == pytest.approx(6.8)


def test_top_cap(store: KuzuGraphStore) -> None:
    top2 = rank_solutions(store, top=2)
    assert [r.solution_id for r in top2] == [SOL_B, SOL_A]
    # top<=0 caps to nothing; top larger than the population returns all four
    assert rank_solutions(store, top=0) == []
    assert len(rank_solutions(store, top=99)) == 4


def test_empty_returns_empty(store: KuzuGraphStore, empty_store: KuzuGraphStore) -> None:
    # a graph with no solutions ranks to []
    assert rank_solutions(empty_store) == []
    # a domain present nowhere is equally graceful (no error, empty result)
    assert rank_solutions(store, domain="no_such_domain") == []


def test_as_dict_shape(store: KuzuGraphStore) -> None:
    top = rank_solutions(store)[0]
    d = top.as_dict()
    assert set(d) == {"solution_id", "name", "score", "evidence_count", "verified_count"}
    assert d["solution_id"] == SOL_B
    assert d["name"] == "Solution B (решение Б)"
    assert d["score"] == pytest.approx(6.8)
    assert d["evidence_count"] == 2
    assert d["verified_count"] == 2


def test_recency_uses_most_recent_year(empty_store: KuzuGraphStore) -> None:
    s = empty_store
    # solution is old (2000) but its evidence is fresh (2025) -> recency follows the max
    s.upsert_node("tech:x", "TechnologySolution", name="X", year=2000)
    s.upsert_node("ev-x", "Evidence", verified=False, year=2025)
    s.upsert_edge("tech:x", "ev-x", "HAS_EVIDENCE")
    ranked = rank_solutions(s)
    assert len(ranked) == 1
    # 1*1 evidence + 0 verified + 1*recency(2025)=1.0 -> 2.0 (not 1.0 from the 2000 solution)
    assert ranked[0].score == pytest.approx(2.0)
    assert ranked[0].name == "X"
