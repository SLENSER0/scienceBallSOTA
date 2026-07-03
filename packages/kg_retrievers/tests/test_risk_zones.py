"""Tests for topic risk-zone classification (§24.15).

Hand-checkable assertions on each risk flag, the score-to-level buckets and the
score-descending / topic-ascending ordering. Тесты зон риска по темам.
"""

from __future__ import annotations

from kg_retrievers.risk_zones import (
    CONTRADICTORY,
    LOW_SOURCES,
    NO_TECHNOECONOMIC,
    STALE,
    TopicRisk,
    classify_topics,
)


def _healthy(topic: str = "t") -> dict[str, object]:
    """A fully-healthy record: no flag should trip (§24.15)."""
    return {
        "topic": topic,
        "source_count": 10,
        "contradiction_count": 0,
        "has_technoeconomic": True,
        "latest_year": 2025,
    }


def test_low_sources_flag() -> None:
    """source_count 1 with min_sources 3 trips 'low_sources' (§24.15)."""
    rec = _healthy() | {"source_count": 1}
    [risk] = classify_topics([rec], current_year=2026, min_sources=3)
    assert LOW_SOURCES in risk.flags
    assert risk.flags == (LOW_SOURCES,)
    assert risk.score == 1
    assert risk.risk_level == "low"


def test_contradictory_flag() -> None:
    """contradiction_count 2 trips 'contradictory' (§24.15)."""
    rec = _healthy() | {"contradiction_count": 2}
    [risk] = classify_topics([rec], current_year=2026)
    assert risk.flags == (CONTRADICTORY,)
    assert risk.risk_level == "low"


def test_no_technoeconomic_flag() -> None:
    """has_technoeconomic False trips 'no_technoeconomic' (§24.15)."""
    rec = _healthy() | {"has_technoeconomic": False}
    [risk] = classify_topics([rec], current_year=2026)
    assert risk.flags == (NO_TECHNOECONOMIC,)


def test_stale_flag() -> None:
    """latest_year 2018, current 2026, stale_years 5 trips 'stale' (§24.15).

    2026 - 2018 == 8 > 5, so the source is stale.
    """
    rec = _healthy() | {"latest_year": 2018}
    [risk] = classify_topics([rec], current_year=2026, stale_years=5)
    assert risk.flags == (STALE,)


def test_stale_boundary_not_tripped() -> None:
    """A source exactly stale_years old is not yet stale (§24.15).

    2026 - 2021 == 5, and staleness needs strictly greater than stale_years.
    """
    rec = _healthy() | {"latest_year": 2021}
    [risk] = classify_topics([rec], current_year=2026, stale_years=5)
    assert STALE not in risk.flags
    assert risk.flags == ()


def test_fully_healthy_topic() -> None:
    """A healthy topic has empty flags, 'none' level and score 0 (§24.15)."""
    [risk] = classify_topics([_healthy()], current_year=2026)
    assert risk.flags == ()
    assert risk.risk_level == "none"
    assert risk.score == 0


def test_two_flag_topic_is_medium() -> None:
    """Two tripped flags yield score 2 and 'medium' (§24.15)."""
    rec = _healthy() | {"source_count": 1, "contradiction_count": 3}
    [risk] = classify_topics([rec], current_year=2026, min_sources=3)
    assert set(risk.flags) == {LOW_SOURCES, CONTRADICTORY}
    assert risk.score == 2
    assert risk.risk_level == "medium"


def test_three_flags_is_high() -> None:
    """Three or more tripped flags yield 'high' (§24.15)."""
    rec = {
        "topic": "danger",
        "source_count": 1,
        "contradiction_count": 4,
        "has_technoeconomic": False,
        "latest_year": 2025,
    }
    [risk] = classify_topics([rec], current_year=2026, min_sources=3)
    assert risk.score == 3
    assert risk.risk_level == "high"


def test_all_four_flags() -> None:
    """All four signals trip together, still 'high' with score 4 (§24.15)."""
    rec = {
        "topic": "worst",
        "source_count": 0,
        "contradiction_count": 1,
        "has_technoeconomic": False,
        "latest_year": 2000,
    }
    [risk] = classify_topics([rec], current_year=2026, min_sources=3, stale_years=5)
    assert risk.score == 4
    assert set(risk.flags) == {LOW_SOURCES, CONTRADICTORY, NO_TECHNOECONOMIC, STALE}
    assert risk.risk_level == "high"


def test_flags_canonical_order() -> None:
    """Flags are always emitted in canonical order (§24.15)."""
    rec = {
        "topic": "ordered",
        "source_count": 0,
        "contradiction_count": 1,
        "has_technoeconomic": False,
        "latest_year": 2000,
    }
    [risk] = classify_topics([rec], current_year=2026)
    assert risk.flags == (LOW_SOURCES, CONTRADICTORY, NO_TECHNOECONOMIC, STALE)


def test_sorted_by_score_descending_then_topic() -> None:
    """Results sort by score desc, then topic asc (§24.15)."""
    records = [
        _healthy("alpha"),
        {  # score 2
            "topic": "bravo",
            "source_count": 1,
            "contradiction_count": 1,
            "has_technoeconomic": True,
            "latest_year": 2025,
        },
        {  # score 2, later topic -> ties broken by topic asc
            "topic": "zulu",
            "source_count": 1,
            "contradiction_count": 1,
            "has_technoeconomic": True,
            "latest_year": 2025,
        },
        {  # score 4
            "topic": "charlie",
            "source_count": 0,
            "contradiction_count": 2,
            "has_technoeconomic": False,
            "latest_year": 2000,
        },
    ]
    result = classify_topics(records, current_year=2026, min_sources=3)
    assert [r.topic for r in result] == ["charlie", "bravo", "zulu", "alpha"]
    assert [r.score for r in result] == [4, 2, 2, 0]


def test_empty_records() -> None:
    """Empty input yields an empty list (§24.15)."""
    assert classify_topics([], current_year=2026) == []


def test_as_dict_shape() -> None:
    """as_dict exposes topic, flags (list), risk_level and score (§24.15)."""
    [risk] = classify_topics([_healthy() | {"source_count": 1}], current_year=2026)
    assert risk.as_dict() == {
        "topic": "t",
        "flags": [LOW_SOURCES],
        "risk_level": "low",
        "score": 1,
    }


def test_topicrisk_is_frozen() -> None:
    """TopicRisk is a frozen dataclass (§24.15)."""
    risk = TopicRisk(topic="t", flags=(), risk_level="none", score=0)
    try:
        risk.score = 5  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("TopicRisk should be frozen")
