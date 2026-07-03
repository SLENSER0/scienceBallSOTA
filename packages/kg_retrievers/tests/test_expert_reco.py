"""Explainable expert recommendation (§24.12).

Hand-checked against a small purpose-built store (no seed dependency): one expert
``Петров П.П.`` is EXPERT_IN a smelting solution that APPLIES_TO the material
``Медь``; two measurements hang off the material and the regime, and a lab carries
the geography. This lets every dimension be traced by eye:

    material="медь"     -> Material(Медь) + its topics {sol, m1}  -> Петров
    domain="pyrometallurgy" -> topics {cu, sol}                   -> Петров
    process="smelting"  -> operation match {sol}                  -> Петров
    geography="russia"  -> practice_type match {sol}              -> Петров

so a full 4-dimension query scores 3+2+1+1 = 7 for Петров, and single-dimension
queries pin the exact reason text.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.expert_reco import DIM_WEIGHT, ExpertRecommendation, recommend_experts
from kg_retrievers.graph_store import KuzuGraphStore

PERSON = make_id("Person", "reco petrov")
LAB = make_id("Lab", "reco copper lab")
CU = make_id("Material", "reco copper")
SOL = make_id("TechnologySolution", "reco copper smelting")
M1 = make_id("Measurement", "reco copper purity")
M2 = make_id("Measurement", "reco smelting temperature")

FULL_CTX = {
    "material": "медь",
    "domain": "pyrometallurgy",
    "process": "smelting",
    "geography": "russia",
}


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    s.upsert_node(PERSON, "Person", name="Петров П.П.", canonical_name="petrov")
    s.upsert_node(LAB, "Lab", name="Лаборатория меди", country="russia", domain="pyrometallurgy")
    s.upsert_node(
        CU,
        "Material",
        name="Медь",
        canonical_name="copper",
        material_class="metal",
        aliases_text="copper|медь|Cu",
        domain="pyrometallurgy",
    )
    s.upsert_node(
        SOL,
        "TechnologySolution",
        name="Плавка меди",
        canonical_name="copper smelting",
        operation="smelting",
        practice_type="russia",
        domain="pyrometallurgy",
    )
    s.upsert_node(
        M1, "Measurement", name="Чистота меди", property_name="purity", domain="pyrometallurgy"
    )
    s.upsert_node(M2, "Measurement", name="Температура плавки", property_name="temperature")
    s.upsert_edge(PERSON, LAB, "MEMBER_OF", confidence=1.0)
    s.upsert_edge(PERSON, SOL, "EXPERT_IN", confidence=0.9)
    s.upsert_edge(SOL, CU, "APPLIES_TO", confidence=0.8)
    s.upsert_edge(M1, CU, "ABOUT_MATERIAL", confidence=0.9)
    s.upsert_edge(M2, SOL, "ABOUT_REGIME", confidence=0.9)
    yield s
    s.close()


def _add_expert(store: KuzuGraphStore, key: str, name: str, topic: str) -> str:
    pid = make_id("Person", key)
    store.upsert_node(pid, "Person", name=name)
    store.upsert_edge(pid, topic, "EXPERT_IN", confidence=0.7)
    return pid


# -- core: ranked, non-empty, explained ------------------------------------
def test_recommend_ranked_nonempty_with_reason(store: KuzuGraphStore) -> None:
    recs = recommend_experts(store, FULL_CTX)
    assert recs  # non-empty
    assert all(isinstance(r, ExpertRecommendation) for r in recs)
    top = recs[0]
    assert top.person_id == PERSON
    assert top.name == "Петров П.П."
    assert top.score > 0
    assert top.reason  # non-empty explanation


# -- score is the summed weight of matched dimensions ----------------------
def test_score_sums_matched_dimension_weights(store: KuzuGraphStore) -> None:
    (rec,) = recommend_experts(store, FULL_CTX)
    # material(3) + domain(2) + process(1) + geography(1) == 7
    assert rec.score == DIM_WEIGHT["material"] + DIM_WEIGHT["domain"] + 1 + 1 == 7
    # reason lists every matched dimension, strongest first (material -> geography).
    assert rec.reason == (
        "общий материал: медь; та же область: pyrometallurgy; "
        "тот же процесс: smelting; та же практика/география: russia"
    )


# -- reason names the matched dimension (single-signal queries) ------------
def test_reason_names_material(store: KuzuGraphStore) -> None:
    (rec,) = recommend_experts(store, {"material": "медь"})
    assert rec.person_id == PERSON
    assert rec.score == DIM_WEIGHT["material"]  # only material matched
    assert "общий материал" in rec.reason
    assert "медь" in rec.reason
    # nothing else leaked into the explanation
    assert "география" not in rec.reason


def test_reason_names_practice_geography(store: KuzuGraphStore) -> None:
    (rec,) = recommend_experts(store, {"geography": "russia"})
    assert rec.person_id == PERSON
    assert rec.score == DIM_WEIGHT["geography"]
    assert "практика/география" in rec.reason
    assert "russia" in rec.reason


# -- descending scores + multi-expert ranking ------------------------------
def test_scores_descending(store: KuzuGraphStore) -> None:
    # Second expert shares only the russia practice via an unrelated solution.
    sol2 = make_id("TechnologySolution", "reco unrelated russia")
    store.upsert_node(
        sol2,
        "TechnologySolution",
        name="Осмотр",
        operation="inspection",
        practice_type="russia",
        domain="environment",
    )
    p2 = _add_expert(store, "reco sidorov", "Сидоров С.С.", sol2)

    recs = recommend_experts(store, FULL_CTX)
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)  # descending
    assert recs[0].person_id == PERSON and recs[0].score == 7
    p2_rec = next(r for r in recs if r.person_id == p2)
    assert p2_rec.score == DIM_WEIGHT["geography"] == 1  # only geography matched


# -- limit respected -------------------------------------------------------
def test_limit_respected(store: KuzuGraphStore) -> None:
    # Six more experts all EXPERT_IN the pyrometallurgy solution -> 7 candidates.
    for i in range(6):
        _add_expert(store, f"reco extra {i}", f"Эксперт-{i}", SOL)
    ctx = {"domain": "pyrometallurgy"}
    assert len(recommend_experts(store, ctx)) == 5  # default limit
    assert len(recommend_experts(store, ctx, limit=2)) == 2
    assert len(recommend_experts(store, ctx, limit=100)) == 7  # all surface


# -- graceful empties ------------------------------------------------------
def test_empty_query_context_returns_empty(store: KuzuGraphStore) -> None:
    assert recommend_experts(store, {}) == []
    assert recommend_experts(store, {"material": "", "domain": "   "}) == []
    assert recommend_experts(store, {"material": None, "process": 42}) == []  # type: ignore[dict-item]
    assert recommend_experts(store, {"unrelated_key": "медь"}) == []


def test_unknown_signals_return_empty(store: KuzuGraphStore) -> None:
    assert recommend_experts(store, {"domain": "no-such-domain"}) == []
    assert recommend_experts(store, {"material": "золото"}) == []  # no gold material seeded
    assert recommend_experts(store, {"process": "no-such-process"}) == []
    assert recommend_experts(store, {"geography": "atlantis"}) == []


# -- serialisation shape ---------------------------------------------------
def test_as_dict_shape(store: KuzuGraphStore) -> None:
    (rec,) = recommend_experts(store, {"material": "медь"})
    d = rec.as_dict()
    assert set(d) == {"person_id", "name", "score", "reason"}
    assert d["person_id"] == PERSON
    assert d["name"] == "Петров П.П."
    assert isinstance(d["score"], int) and d["score"] == DIM_WEIGHT["material"]
    assert isinstance(d["reason"], str) and d["reason"]
