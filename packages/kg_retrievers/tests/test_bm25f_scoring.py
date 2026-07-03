"""Tests for field-weighted BM25F scoring (§12.3, Mode B).

Hand-checkable: the single-field, boost=1, b=0, len=avglen case must reduce to
plain BM25 ``idf·tf/(k1+tf)``; boosts, length normalisation and joint saturation
are each pinned to an explicit arithmetic expectation.
"""

from __future__ import annotations

from kg_retrievers.bm25f_scoring import BM25FScore, score_bm25f


def test_single_field_reduces_to_plain_bm25() -> None:
    """boost=1, b=0, len=avglen → term score is idf·tf/(k1+tf) (§12.3)."""
    cfg = {"body": (1.0, 0.0, 10.0)}
    res = score_bm25f(
        "d1",
        ["steel"],
        field_tf={"body": {"steel": 3}},
        field_len={"body": 10},
        field_cfg=cfg,
        idf_map={"steel": 2.0},
        k1=1.2,
    )
    expected = 2.0 * 3 / (1.2 + 3)
    assert res.per_term["steel"] == expected
    assert res.score == expected


def test_doubling_boost_strictly_raises_contribution() -> None:
    """Doubling a field's boost raises that term's contribution (§12.3)."""
    tf = {"title": {"alloy": 2}}
    length = {"title": 8}
    idf = {"alloy": 1.5}
    low = score_bm25f("d", ["alloy"], tf, length, {"title": (1.0, 0.0, 8.0)}, idf)
    high = score_bm25f("d", ["alloy"], tf, length, {"title": (2.0, 0.0, 8.0)}, idf)
    assert high.per_term["alloy"] > low.per_term["alloy"]


def test_length_normalisation_penalises_long_doc() -> None:
    """With b>0 a doc longer than avglen scores below an avg-length doc (§12.3)."""
    cfg = {"body": (1.0, 0.75, 10.0)}
    idf = {"metal": 1.0}
    avg = score_bm25f("avg", ["metal"], {"body": {"metal": 4}}, {"body": 10}, cfg, idf)
    long = score_bm25f("long", ["metal"], {"body": {"metal": 4}}, {"body": 40}, cfg, idf)
    assert long.per_term["metal"] < avg.per_term["metal"]


def test_absent_term_contributes_zero() -> None:
    """A query term absent from the document contributes 0.0 (§12.3)."""
    res = score_bm25f(
        "d1",
        ["missing"],
        field_tf={"body": {"steel": 3}},
        field_len={"body": 10},
        field_cfg={"body": (1.0, 0.0, 10.0)},
        idf_map={"missing": 5.0},
    )
    assert res.per_term["missing"] == 0.0
    assert res.score == 0.0


def test_zero_idf_term_contributes_zero() -> None:
    """A term with idf 0 contributes 0.0 regardless of frequency (§12.3)."""
    res = score_bm25f(
        "d1",
        ["common"],
        field_tf={"body": {"common": 7}},
        field_len={"body": 10},
        field_cfg={"body": (1.0, 0.0, 10.0)},
        idf_map={"common": 0.0},
    )
    assert res.per_term["common"] == 0.0
    assert res.score == 0.0


def test_two_fields_combine_before_saturation() -> None:
    """Two fields' tf combine before k1 saturation, not summed post-saturation (§12.3)."""
    cfg = {
        "title": (1.0, 0.0, 5.0),
        "body": (1.0, 0.0, 20.0),
    }
    tf = {"title": {"copper": 2}, "body": {"copper": 3}}
    length = {"title": 5, "body": 20}
    idf = {"copper": 1.0}
    res = score_bm25f("d", ["copper"], tf, length, cfg, idf, k1=1.2)

    # tf̃ = 1*2/1 + 1*3/1 = 5 (both b=0, len=avglen). Joint saturation:
    combined = 5.0 / (1.2 + 5.0)
    assert res.per_term["copper"] == combined

    # Summing the two fields *after* saturating each separately would give a
    # strictly different (here larger) value — this proves tf combines first.
    post_sat = 2.0 / (1.2 + 2.0) + 3.0 / (1.2 + 3.0)
    assert combined != post_sat
    assert combined < post_sat


def test_score_is_sum_of_per_term() -> None:
    """Total score equals Σ per_term values across query terms (§12.3)."""
    cfg = {"body": (1.0, 0.0, 10.0)}
    tf = {"body": {"steel": 2, "alloy": 4}}
    length = {"body": 10}
    idf = {"steel": 2.0, "alloy": 1.5}
    res = score_bm25f("d", ["steel", "alloy", "steel"], tf, length, cfg, idf)
    assert res.score == sum(res.per_term.values())
    # Duplicate query term collapses to a single per_term key.
    assert list(res.per_term) == ["steel", "alloy"]


def test_as_dict_exposes_fields() -> None:
    """as_dict() exposes {doc_id, score, per_term} (§12.3)."""
    res = score_bm25f(
        "d9",
        ["steel"],
        {"body": {"steel": 1}},
        {"body": 10},
        {"body": (1.0, 0.0, 10.0)},
        {"steel": 1.0},
    )
    d = res.as_dict()
    assert d == {"doc_id": "d9", "score": res.score, "per_term": {"steel": res.per_term["steel"]}}
    # Frozen dataclass round-trip on the exposed shape.
    assert isinstance(res, BM25FScore)
    assert set(d) == {"doc_id", "score", "per_term"}
