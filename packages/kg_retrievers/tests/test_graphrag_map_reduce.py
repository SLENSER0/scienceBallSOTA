"""GraphRAG map-reduce reduce step (§11.7).

Hand-checkable reduce over map partials: thresholding + drop count, relevance
ordering, finding dedup/truncation, and the sorted document-id union.
"""

from __future__ import annotations

import json

from kg_retrievers.graphrag_map_reduce import (
    ReducedAnswer,
    reduce_partials,
    select_partials,
)


def _p(cid: int, rel: float, findings: list[str], docs: list[str]) -> dict:
    return {"community_id": cid, "relevance": rel, "findings": findings, "doc_ids": docs}


def test_below_threshold_dropped_and_counted() -> None:
    partials = [
        _p(1, 0.9, ["a"], ["d1"]),
        _p(2, 0.05, ["b"], ["d2"]),  # below default min_relevance 0.1
        _p(3, 0.5, ["c"], ["d3"]),
    ]
    ans = reduce_partials(partials)
    assert set(ans.used_community_ids) == {1, 3}
    assert 2 not in ans.used_community_ids
    assert ans.dropped == 1


def test_survivors_ordered_by_relevance_desc() -> None:
    partials = [
        _p(10, 0.3, ["x"], []),
        _p(20, 0.9, ["y"], []),
        _p(30, 0.6, ["z"], []),
    ]
    ans = reduce_partials(partials)
    assert ans.used_community_ids == (20, 30, 10)


def test_duplicate_findings_appear_once() -> None:
    partials = [
        _p(1, 0.9, ["shared", "one"], []),
        _p(2, 0.5, ["shared", "two"], []),
    ]
    ans = reduce_partials(partials)
    # first-seen order across relevance-ordered survivors; "shared" only once.
    assert ans.findings == ("shared", "one", "two")
    assert ans.findings.count("shared") == 1


def test_findings_truncated_to_max_findings() -> None:
    partials = [_p(1, 0.9, [f"f{i}" for i in range(50)], [])]
    ans = reduce_partials(partials, max_findings=5)
    assert ans.findings == ("f0", "f1", "f2", "f3", "f4")
    assert len(ans.findings) == 5


def test_cited_doc_ids_is_sorted_union() -> None:
    partials = [
        _p(1, 0.9, [], ["z-doc", "a-doc"]),
        _p(2, 0.5, [], ["m-doc", "a-doc"]),  # a-doc duplicated across partials
    ]
    ans = reduce_partials(partials)
    assert ans.cited_doc_ids == ("a-doc", "m-doc", "z-doc")


def test_all_below_threshold_yields_empty_and_full_dropped() -> None:
    partials = [
        _p(1, 0.01, ["a"], ["d1"]),
        _p(2, 0.02, ["b"], ["d2"]),
    ]
    ans = reduce_partials(partials, min_relevance=0.1)
    assert ans.used_community_ids == ()
    assert ans.findings == ()
    assert ans.cited_doc_ids == ()
    assert ans.dropped == len(partials) == 2


def test_as_dict_json_serializable() -> None:
    partials = [_p(1, 0.9, ["a", "b"], ["d1", "d2"])]
    ans = reduce_partials(partials)
    d = ans.as_dict()
    assert set(d) == {"used_community_ids", "findings", "cited_doc_ids", "dropped"}
    encoded = json.dumps(d)  # must not raise
    assert json.loads(encoded) == d
    assert isinstance(d["used_community_ids"], list)
    assert isinstance(d["findings"], list)
    assert isinstance(d["cited_doc_ids"], list)
    assert isinstance(d["dropped"], int)


def test_select_partials_filters_and_orders() -> None:
    partials = [
        _p(1, 0.2, [], []),
        _p(2, 0.05, [], []),
        _p(3, 0.8, [], []),
    ]
    survivors = select_partials(partials, 0.1)
    assert [p["community_id"] for p in survivors] == [3, 1]


def test_reduce_returns_reduced_answer_type() -> None:
    ans = reduce_partials([_p(1, 0.9, ["a"], ["d1"])])
    assert isinstance(ans, ReducedAnswer)
    assert ans.used_community_ids == (1,)
    assert ans.findings == ("a",)
    assert ans.cited_doc_ids == ("d1",)
    assert ans.dropped == 0
