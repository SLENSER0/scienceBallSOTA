"""Source freshness / staleness classification tests (§10.7)."""

from __future__ import annotations

from datetime import datetime

from kg_common.source_freshness import (
    LEVELS,
    Freshness,
    classify,
    rank,
    stalest,
)


def dt(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d)


def test_fresh_two_days_old() -> None:
    f = classify("s", dt(2026, 7, 1), dt(2026, 7, 3))
    assert f.level == "fresh"
    assert f.age_days == 2
    assert f.source_id == "s"
    assert f.last_ingest_at == "2026-07-01T00:00:00"


def test_aging_two_months_old() -> None:
    f = classify("s", dt(2026, 5, 1), dt(2026, 7, 3))
    assert f.level == "aging"
    # 31 (May) + 30 (June) + 2 (to Jul 3) = 63 days.
    assert f.age_days == 63


def test_stale_over_a_year_old() -> None:
    f = classify("s", dt(2025, 1, 1), dt(2026, 7, 3))
    assert f.level == "stale"
    assert f.age_days is not None and f.age_days > 180


def test_unknown_when_never_ingested() -> None:
    f = classify("s", None, dt(2026, 7, 3))
    assert f.level == "unknown"
    assert f.age_days is None
    assert f.last_ingest_at is None


def test_fresh_boundary_exactly_30_days() -> None:
    # Exactly fresh_days old is still fresh (inclusive lower boundary).
    f = classify("s", dt(2026, 6, 3), dt(2026, 7, 3))
    assert f.age_days == 30
    assert f.level == "fresh"


def test_aging_at_31_days() -> None:
    # One day past the fresh boundary tips into aging.
    f = classify("s", dt(2026, 6, 2), dt(2026, 7, 3))
    assert f.age_days == 31
    assert f.level == "aging"


def test_aging_boundary_exactly_180_days() -> None:
    f = classify("s", dt(2026, 1, 4), dt(2026, 7, 3))
    assert f.age_days == 180
    assert f.level == "aging"


def test_stale_at_181_days() -> None:
    f = classify("s", dt(2026, 1, 3), dt(2026, 7, 3))
    assert f.age_days == 181
    assert f.level == "stale"


def test_custom_thresholds() -> None:
    f = classify("s", dt(2026, 6, 26), dt(2026, 7, 3), fresh_days=7, stale_days=14)
    assert f.age_days == 7
    assert f.level == "fresh"
    g = classify("s", dt(2026, 6, 25), dt(2026, 7, 3), fresh_days=7, stale_days=14)
    assert g.age_days == 8
    assert g.level == "aging"


def test_rank_ordering() -> None:
    assert rank(Freshness("s", "2026-07-01T00:00:00", 2, "fresh")) == 0
    assert rank(Freshness("s", "2026-05-01T00:00:00", 63, "aging")) == 1
    assert rank(Freshness("s", "2025-01-01T00:00:00", 548, "stale")) == 2
    assert rank(Freshness("s", None, None, "unknown")) == 3


def test_stalest_picks_worse_by_rank() -> None:
    fresh = classify("a", dt(2026, 7, 1), dt(2026, 7, 3))
    stale = classify("b", dt(2025, 1, 1), dt(2026, 7, 3))
    assert stalest([fresh, stale]) == stale
    # Order of the inputs does not matter.
    assert stalest([stale, fresh]) == stale


def test_stalest_unknown_outranks_stale() -> None:
    stale = classify("b", dt(2025, 1, 1), dt(2026, 7, 3))
    unknown = classify("c", None, dt(2026, 7, 3))
    assert stalest([stale, unknown]) == unknown


def test_stalest_tie_broken_by_age() -> None:
    older = classify("old", dt(2025, 1, 1), dt(2026, 7, 3))
    newer = classify("new", dt(2025, 6, 1), dt(2026, 7, 3))
    assert older.level == newer.level == "stale"
    assert stalest([newer, older]) == older


def test_stalest_empty_is_none() -> None:
    assert stalest([]) is None


def test_as_dict_shape() -> None:
    d = classify("s", dt(2026, 7, 1), dt(2026, 7, 3)).as_dict()
    assert "level" in d
    assert "age_days" in d
    assert d == {
        "source_id": "s",
        "last_ingest_at": "2026-07-01T00:00:00",
        "age_days": 2,
        "level": "fresh",
    }


def test_levels_constant() -> None:
    assert LEVELS == ("fresh", "aging", "stale", "unknown")
