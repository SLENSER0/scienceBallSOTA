"""§12.6 — hand-checked tests for evidence-quality-v2 (span / source_type / review).

Every expected value is computed by hand from the §12.6 convex combination
(weights ``core=0.40, source=0.20, span=0.20, verified=0.20``):

    score = 0.40·(strength·conf) + 0.20·source + 0.20·span + 0.20·verified

with ``rejected`` short-circuiting to ``0.0``.
"""

from __future__ import annotations

from kg_retrievers.evidence_quality import (
    REJECTED_SCORE,
    WEIGHTS,
    QualityWeights,
    evidence_quality_breakdown,
    evidence_quality_v2,
    has_span,
)


def test_span_present_strictly_beats_span_absent_all_else_equal() -> None:
    # strength patent=0.8, conf 0.5 → core 0.4; paragraph 0.7; pending 0.5.
    base = {
        "evidence_strength": "patent",
        "confidence": 0.5,
        "source_type": "paragraph",
        "review_status": "pending",
    }
    without = evidence_quality_v2(base)
    with_span = evidence_quality_v2({**base, "char_start": 10, "char_end": 20})
    # 0.40·0.4 + 0.20·0.7 + 0.20·0 + 0.20·0.5 = 0.40
    assert without == 0.40
    # + 0.20·1.0 span
    assert with_span == 0.60
    assert with_span > without


def test_table_row_col_counts_as_span() -> None:
    base = {
        "evidence_strength": "patent",
        "confidence": 0.5,
        "source_type": "paragraph",
        "review_status": "pending",
    }
    with_cell = evidence_quality_v2({**base, "row": 2, "col": 3})
    assert with_cell == 0.60  # same as a char span
    # a lone row (no col) is NOT a span
    assert has_span({**base, "row": 2}) is False
    assert evidence_quality_v2({**base, "row": 2}) == 0.40


def test_char_start_zero_is_present_not_falsy() -> None:
    base = {
        "evidence_strength": "patent",
        "confidence": 0.5,
        "source_type": "paragraph",
        "review_status": "pending",
    }
    # char_start == 0 must count as present (guards against truthiness bugs).
    assert has_span({**base, "char_start": 0, "char_end": 0}) is True
    assert evidence_quality_v2({**base, "char_start": 0, "char_end": 0}) == 0.60


def test_source_type_ordering_table_cell_paragraph_figure_metadata() -> None:
    # strength standard=0.7, conf 0.6 → core 0.42; no span; pending 0.5.
    base = {"evidence_strength": "standard", "confidence": 0.6, "review_status": "pending"}
    table = evidence_quality_v2({**base, "source_type": "table_cell"})
    para = evidence_quality_v2({**base, "source_type": "paragraph"})
    fig = evidence_quality_v2({**base, "source_type": "figure_caption"})
    meta = evidence_quality_v2({**base, "source_type": "metadata"})
    # 0.40·0.42 + 0.20·src + 0.20·0.5(pending) = 0.168 + 0.20·src + 0.10
    assert table == 0.468  # src 1.0
    assert para == 0.408  # src 0.7
    assert fig == 0.348  # src 0.4
    assert meta == 0.298  # src 0.15
    assert table > para > fig > meta


def test_rejected_scores_near_zero_regardless_of_strength() -> None:
    strong = {
        "evidence_strength": "peer_reviewed",
        "confidence": 1.0,
        "source_type": "table_cell",
        "char_start": 0,
        "char_end": 5,
        "review_status": "rejected",
    }
    weak = {"evidence_strength": "unverified", "confidence": 0.1, "review_status": "rejected"}
    assert evidence_quality_v2(strong) == REJECTED_SCORE == 0.0
    assert evidence_quality_v2(weak) == 0.0
    # rejected via a boolean flag also tanks it
    assert evidence_quality_v2({"evidence_strength": "peer_reviewed", "rejected": True}) == 0.0
    # and it is strictly below the same hit when not rejected (no status → neutral 0.5)
    # 0.40·1.0 + 0.20·1.0 + 0.20·1.0 + 0.20·0.5 = 0.90
    not_rejected = evidence_quality_v2({k: v for k, v in strong.items() if k != "review_status"})
    assert not_rejected == 0.90
    assert evidence_quality_v2(strong) < not_rejected


def test_verified_beats_pending_all_else_equal() -> None:
    # strength conference=0.5, conf 0.6 → core 0.3; paragraph 0.7; no span.
    base = {"evidence_strength": "conference", "confidence": 0.6, "source_type": "paragraph"}
    pending = evidence_quality_v2({**base, "review_status": "pending"})
    accepted = evidence_quality_v2({**base, "review_status": "accepted"})
    flagged = evidence_quality_v2({**base, "verified": True})
    # 0.40·0.3 + 0.20·0.7 = 0.12 + 0.14 = 0.26; + 0.20·verified
    assert pending == 0.36  # verified 0.5
    assert accepted == 0.46  # verified 1.0
    assert flagged == 0.46  # boolean flag == accepted status
    assert accepted > pending


def test_scores_are_bounded_and_max_reaches_one() -> None:
    samples = [
        {},
        {"evidence_strength": "peer_reviewed", "confidence": 1.0},
        {"confidence": -5.0},  # clamps to 0.0
        {"confidence": 42.0},  # clamps to 1.0
        {"evidence_strength": "unknown_kind", "source_type": "mystery"},
        {"review_status": "rejected"},
    ]
    for ev in samples:
        assert 0.0 <= evidence_quality_v2(ev) <= 1.0
    top = {
        "evidence_strength": "peer_reviewed",
        "confidence": 1.0,
        "source_type": "table_cell",
        "char_start": 3,
        "char_end": 9,
        "review_status": "verified",
    }
    # 0.40·1.0 + 0.20·1.0 + 0.20·1.0 + 0.20·1.0 = 1.0
    assert evidence_quality_v2(top) == 1.0


def test_strong_span_verified_scores_near_top() -> None:
    ev = {
        "evidence_strength": "peer_reviewed",
        "confidence": 0.95,
        "source_type": "table_cell",
        "char_start": 3,
        "char_end": 9,
        "review_status": "verified",
    }
    # 0.40·0.95 + 0.20·1.0 + 0.20·1.0 + 0.20·1.0 = 0.38 + 0.60 = 0.98
    assert evidence_quality_v2(ev) == 0.98
    assert evidence_quality_v2(ev) >= 0.9


def test_missing_fields_default_sanely() -> None:
    # strength 0.3, conf 0.6 → core 0.18; source default 0.5; no span; neutral 0.5.
    # 0.40·0.18 + 0.20·0.5 + 0.20·0 + 0.20·0.5 = 0.072 + 0.10 + 0.10 = 0.272
    assert evidence_quality_v2({}) == 0.272
    assert 0.0 <= evidence_quality_v2({}) <= 1.0


def test_no_span_metadata_rejected_is_minimal() -> None:
    minimal = evidence_quality_v2(
        {
            "evidence_strength": "peer_reviewed",
            "confidence": 1.0,
            "source_type": "metadata",
            "review_status": "rejected",
        }
    )
    assert minimal == 0.0  # rejected override → the global floor
    # every other (non-rejected) case sits strictly above the rejected floor
    others = [
        evidence_quality_v2({}),
        evidence_quality_v2({"source_type": "metadata"}),
        evidence_quality_v2({"source_type": "metadata", "review_status": "pending"}),
    ]
    assert all(o > minimal for o in others)


def test_breakdown_is_consistent_and_serialisable() -> None:
    ev = {
        "evidence_strength": "patent",
        "confidence": 0.5,
        "source_type": "table_cell",
        "char_start": 4,
        "char_end": 12,
        "review_status": "accepted",
    }
    bd = evidence_quality_breakdown(ev)
    assert bd.score == evidence_quality_v2(ev)
    assert bd.span_present is True
    assert bd.rejected is False
    assert bd.strength == 0.8
    assert bd.confidence == 0.5
    assert bd.core == 0.4
    assert bd.source_type_score == 1.0
    assert bd.verified_score == 1.0
    # 0.40·0.4 + 0.20·1.0 + 0.20·1.0 + 0.20·1.0 = 0.16 + 0.60 = 0.76
    assert bd.score == 0.76
    d = bd.as_dict()
    assert d["score"] == 0.76 and d["span_present"] is True
    assert set(d["weights"]) == {"core", "source", "span", "verified"}


def test_weights_must_sum_to_one() -> None:
    assert WEIGHTS.as_dict() == {"core": 0.40, "source": 0.20, "span": 0.20, "verified": 0.20}
    try:
        QualityWeights(core=0.5, source=0.5, span=0.5, verified=0.5)
    except ValueError:
        pass
    else:  # pragma: no cover - guard must raise
        raise AssertionError("QualityWeights that do not sum to 1.0 must raise")
