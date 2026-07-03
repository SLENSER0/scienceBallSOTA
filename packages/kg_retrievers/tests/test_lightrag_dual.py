"""Tests for LightRAG dual-level keyword retrieval (§11.12 / §12).

Paper under test: LightRAG (arXiv:2410.05779). A small hand-built temp Kuzu store
gives fully checkable low-level (entity-name) and high-level (label/domain) hits.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers import lightrag_dual
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.lightrag_dual import (
    DualKeywords,
    DualResult,
    dual_retrieve,
    extract_keywords,
)

# -- deterministic node ids (hand-checkable) --------------------------------
RO = make_id("TechnologySolution", "reverse osmosis")  # tech:reverse-osmosis
IX = make_id("TechnologySolution", "ion exchange")  # tech:ion-exchange
NICKEL = make_id("Material", "nickel")  # material:nickel
HEAP = make_id("Method", "heap leaching")  # method:heap-leaching
MEMBRANE = make_id("Material", "membrane")  # material:membrane


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    """A tiny hand-built store: water-treatment techs + metallurgy materials."""
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    s.upsert_node(
        RO,
        "TechnologySolution",
        name="Reverse Osmosis",
        canonical_name="reverse osmosis",
        aliases_text="RO|обратный осмос",
        domain="water_treatment",
    )
    s.upsert_node(
        IX,
        "TechnologySolution",
        name="Ion Exchange",
        canonical_name="ion exchange",
        aliases_text="ионный обмен",
        domain="water_treatment",
    )
    s.upsert_node(
        NICKEL,
        "Material",
        name="Nickel",
        canonical_name="nickel",
        aliases_text="никель|Ni",
        domain="metallurgy",
    )
    s.upsert_node(
        HEAP,
        "Method",
        name="Heap Leaching",
        canonical_name="heap leaching",
        domain="metallurgy",
    )
    s.upsert_node(
        MEMBRANE,
        "Material",
        name="Membrane",
        canonical_name="membrane",
        aliases_text="мембрана",
        domain="water_treatment",
    )
    yield s
    s.close()


# -- extract_keywords --------------------------------------------------------
def test_extract_splits_low_and_high() -> None:
    kw = extract_keywords("reverse osmosis technology metallurgy")
    assert isinstance(kw, DualKeywords)
    # specific entity tokens land in low; broad theme/domain tokens in high
    assert "osmosis" in kw.low_level
    assert "reverse" in kw.low_level
    assert "technology" in kw.high_level
    assert "metallurgy" in kw.high_level
    # a token is never in both buckets
    assert set(kw.low_level).isdisjoint(kw.high_level)


def test_extract_dedup_and_lowercase() -> None:
    kw = extract_keywords("Osmosis OSMOSIS osmosis Technology TECHNOLOGY")
    assert kw.low_level == ("osmosis",)  # lowercased + deduped
    assert kw.high_level == ("technology",)


def test_extract_empty_and_stopwords_graceful() -> None:
    assert extract_keywords("") == DualKeywords((), ())
    assert extract_keywords("   ") == DualKeywords((), ())
    # a query of only stop-words yields no keys at all
    assert extract_keywords("the of and или для") == DualKeywords((), ())


# -- dual_retrieve -----------------------------------------------------------
def test_dual_retrieve_returns_both_and_merged(store: KuzuGraphStore) -> None:
    res = dual_retrieve(store, "osmosis technology", top_k=8)
    assert isinstance(res, DualResult)
    assert res.low_hits, "expected low-level entity-name hits"
    assert res.high_hits, "expected high-level label/domain hits"
    assert res.merged, "expected an RRF-merged list"
    # merged is sorted by descending RRF score (stable)
    scores = [h.score for h in res.merged]
    assert scores == sorted(scores, reverse=True)


def test_entity_query_hits_low(store: KuzuGraphStore) -> None:
    # a concrete entity mention (RU alias) drives the low-level entity-name lookup
    res = dual_retrieve(store, "никель", top_k=8)
    assert [h.id for h in res.low_hits] == [NICKEL]
    assert res.high_hits == ()  # no broad theme token → empty high channel
    assert res.merged[0].id == NICKEL


def test_thematic_query_hits_high(store: KuzuGraphStore) -> None:
    # broad theme/domain tokens drive the label/domain scan, not the name lookup
    res = dual_retrieve(store, "technology metallurgy", top_k=8)
    assert res.low_hits == ()  # no specific entity token → empty low channel
    high_ids = {h.id for h in res.high_hits}
    assert RO in high_ids and IX in high_ids  # matched label TechnologySolution
    assert NICKEL in high_ids and HEAP in high_ids  # matched domain metallurgy


def test_rrf_merge_dedups(store: KuzuGraphStore) -> None:
    # "osmosis" (low, entity name) and "technology" (high, label) both hit RO
    res = dual_retrieve(store, "osmosis technology", top_k=8)
    assert RO in {h.id for h in res.low_hits}
    assert RO in {h.id for h in res.high_hits}
    ro_merged = [h for h in res.merged if h.id == RO]
    assert len(ro_merged) == 1, "RO must be de-duplicated across channels"
    hit = ro_merged[0]
    assert set(hit.channels) == {"low", "high"}  # contributed by both channels
    # a two-channel RRF score strictly exceeds any single-channel contribution
    assert hit.score > 1.0 / (lightrag_dual.DEFAULT_RRF_K + 1)


def test_empty_query_graceful(store: KuzuGraphStore) -> None:
    res = dual_retrieve(store, "   ", top_k=8)
    assert res.low_hits == ()
    assert res.high_hits == ()
    assert res.merged == ()


def test_as_dict_shapes(store: KuzuGraphStore) -> None:
    kw = extract_keywords("osmosis technology")
    kd = kw.as_dict()
    assert kd == {"low_level": ["osmosis"], "high_level": ["technology"]}
    assert isinstance(kd["low_level"], list)

    res = dual_retrieve(store, "osmosis technology", top_k=8)
    rd = res.as_dict()
    assert set(rd) == {"low_hits", "high_hits", "merged"}
    assert all(isinstance(v, list) for v in rd.values())
    merged0 = rd["merged"][0]
    assert set(merged0) == {"id", "name", "score", "channels"}
    assert isinstance(merged0["channels"], list)
    low0 = rd["low_hits"][0]
    assert set(low0) == {"id", "name", "label", "matched", "score"}


def test_paper_cited_in_docstring() -> None:
    # Hard requirement: the module must cite its source paper (arXiv id).
    assert "2410.05779" in (lightrag_dual.__doc__ or "")
