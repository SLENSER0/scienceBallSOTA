"""Tests for SPLADE-lite sparse lexical vectors (§4.4).

All expected values are hand-derivable: a token's log-TF weight is ``1 + ln(tf)``
(so ``tf == 1`` → ``1.0``), and the corpus IDF is ``ln((N + 1) / (df + 1))`` (so a
term in every one of ``N`` docs → ``ln 1 == 0``).
"""

from __future__ import annotations

import math

from kg_retrievers.sparse import SparseIndex, sparse_dot, sparse_vector


def test_sparse_vector_nonzero_for_content_tokens() -> None:
    """Content tokens survive with the expected log-TF weights (§4.4)."""
    vec = sparse_vector("hardness corrosion corrosion")
    assert set(vec) == {"hardness", "corrosion"}
    assert vec["hardness"] == 1.0  # tf == 1 -> 1 + ln(1)
    assert vec["corrosion"] == 1.0 + math.log(2)  # tf == 2
    assert vec["corrosion"] > vec["hardness"]


def test_sparse_vector_empty_for_stopwords_and_short() -> None:
    """Stopword-only and too-short text fold to an empty vector (§4.4)."""
    assert sparse_vector("the and for из для или") == {}
    assert sparse_vector("a of to и в на") == {}  # all shorter than 3 chars
    assert sparse_vector("   ") == {}


def test_sparse_dot_identical_beats_disjoint() -> None:
    """Self-overlap outscores disjoint vocabularies (§4.4)."""
    a = sparse_vector("aluminum copper hardness")
    same = sparse_dot(a, a)
    disjoint = sparse_dot(a, sparse_vector("polymer membrane fouling"))
    assert disjoint == 0.0
    assert same > disjoint
    assert same > 0.0


def test_search_ranks_matching_doc_first() -> None:
    """The document sharing the query's tokens ranks first (§4.4)."""
    idx = SparseIndex()
    idx.add("d1", "aluminum copper hardness measurement")
    idx.add("d2", "polymer membrane fouling desalination")
    idx.add("d3", "reactor thermal cycling fatigue")
    hits = idx.search("copper hardness", limit=10)
    assert hits, "expected at least one hit"
    assert hits[0][0] == "d1"
    assert all(score > 0.0 for _, score in hits)


def test_idf_downweights_term_present_in_all_docs() -> None:
    """A term in every document has IDF 0 and cannot rank a doc (§4.4)."""
    idx = SparseIndex()
    idx.add("d1", "common alpha alpha")
    idx.add("d2", "common beta")
    idx.add("d3", "common gamma")
    assert idx.idf("common") == 0.0  # df == N == 3 -> ln(4/4)
    assert idx.idf("alpha") > 0.0  # df == 1 -> ln(4/2) > 0
    # "common" alone matches every doc but scores 0 -> no hits survive.
    assert idx.search("common") == []
    # Adding a discriminating token pulls exactly its owning doc to the top.
    hits = idx.search("common alpha")
    assert [doc for doc, _ in hits] == ["d1"]


def test_ru_and_en_tokens_both_indexed() -> None:
    """Mixed RU/EN text yields both language tokens and is searchable (§4.4)."""
    vec = sparse_vector("aluminum алюминий hardness прочность")
    assert {"aluminum", "алюминий", "hardness", "прочность"} <= set(vec)
    idx = SparseIndex()
    idx.add("ru", "коррозия мембрана опреснение")
    idx.add("en", "corrosion membrane desalination")
    assert idx.search("коррозия")[0][0] == "ru"
    assert idx.search("corrosion")[0][0] == "en"


def test_add_and_search_multiple_docs() -> None:
    """Building a small corpus and querying it returns ordered hits (§4.4)."""
    idx = SparseIndex()
    docs = {
        "a": "titanium alloy strength fatigue",
        "b": "titanium coating corrosion resistance",
        "c": "concrete curing shrinkage",
    }
    for doc_id, text in docs.items():
        idx.add(doc_id, text)
    assert len(idx) == 3
    hits = idx.search("titanium corrosion", limit=2)
    ids = [doc for doc, _ in hits]
    assert ids[0] == "b"  # shares both "titanium" and rarer "corrosion"
    assert "c" not in ids  # shares nothing with the query


def test_empty_index_returns_empty() -> None:
    """An index with no documents yields no hits (§4.4)."""
    assert SparseIndex().search("anything at all") == []


def test_unknown_query_returns_empty() -> None:
    """A query whose tokens are absent from the corpus yields no hits (§4.4)."""
    idx = SparseIndex()
    idx.add("d1", "aluminum copper hardness")
    assert idx.search("polymer membrane fouling") == []
    assert idx.search("для или это") == []  # stopword-only query folds to nothing
