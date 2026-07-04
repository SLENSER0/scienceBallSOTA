"""TTL-cache tests for ``GET /coverage/dashboard`` (§15.5 / §5.2.7).

RU: короткий TTL-кэш поверх двух тяжёлых полнографовых агрегаторов
(``build_coverage_timeline`` — 3 обхода, ``aggregate_gaps_by_owner`` — ещё один)
не меняет ответ, пересчитывает их 1 раз на TTL-окно, а ``owner_limit`` по-прежнему
режет уже готовый список из кэша (без повторного расчёта).

EN: the short TTL cache over the two heavy full-graph aggregators must be
behavior-preserving — identical response, aggregators run once per TTL window,
and ``owner_limit`` still slices the cached owner list without recomputing.
"""

from __future__ import annotations

from api_gateway.routers import coverage_dashboard as cd

import kg_retrievers.coverage_matrix as cm
from kg_retrievers.coverage_matrix import CoverageTimelinePoint, GapByOwner


class _DummyStore:
    """Minimal store stand-in: only ``db_path`` is used (as the cache key)."""

    db_path = "memtest://coverage-dashboard"


def _sample() -> tuple[list[CoverageTimelinePoint], list[GapByOwner]]:
    points = [
        CoverageTimelinePoint(year=2020, paper_count=3, measurement_count=4, gap_count=1),
        CoverageTimelinePoint(year=2021, paper_count=1, measurement_count=0, gap_count=2),
    ]
    owners = [
        GapByOwner(
            owner="hydro", lab_id="L1", lab_name="Hydro Lab", gap_count=2, gap_ids=("g1", "g2")
        ),
        GapByOwner(
            owner="pyro",
            lab_id=None,
            lab_name=None,
            gap_count=5,
            gap_ids=("g3", "g4", "g5", "g6", "g7"),
        ),
        GapByOwner(
            owner="unassigned", lab_id=None, lab_name=None, gap_count=1, gap_ids=("g8",)
        ),
    ]
    return points, owners


def _install(monkeypatch, points, owners) -> dict[str, int]:
    """Wire call-counting fakes for both aggregators + a dummy store; clear cache."""
    calls = {"timeline": 0, "owners": 0}

    def fake_timeline(store):
        calls["timeline"] += 1
        return points

    def fake_owners(store):
        calls["owners"] += 1
        return owners

    # ``_coverage_aggregates`` does ``from kg_retrievers.coverage_matrix import ...``
    # at call time, so patching the module attributes is picked up.
    monkeypatch.setattr(cm, "build_coverage_timeline", fake_timeline)
    monkeypatch.setattr(cm, "aggregate_gaps_by_owner", fake_owners)
    monkeypatch.setattr(cd, "get_store", lambda: _DummyStore())
    cd._cache.clear()
    return calls


def test_aggregators_run_once_per_ttl_window(monkeypatch) -> None:
    """2-й запрос в TTL-окне не пересчитывает агрегаторы / cache hit (§15.5)."""
    points, owners = _sample()
    calls = _install(monkeypatch, points, owners)
    r1 = cd.coverage_dashboard(owner_limit=None)
    r2 = cd.coverage_dashboard(owner_limit=None)
    assert calls == {"timeline": 1, "owners": 1}  # 2nd served from cache
    assert r1 == r2  # identical response


def test_cache_matches_recompute(monkeypatch) -> None:
    """Ответ не зависит от состояния кэша / cached == recomputed (§15.5)."""
    points, owners = _sample()
    calls = _install(monkeypatch, points, owners)
    cached_first = cd.coverage_dashboard(owner_limit=None)  # miss → computes + stores
    cd._cache.clear()  # force a full recompute
    recomputed = cd.coverage_dashboard(owner_limit=None)  # miss again
    assert cached_first == recomputed
    assert calls == {"timeline": 2, "owners": 2}


def test_owner_limit_slices_cached_list_without_recompute(monkeypatch) -> None:
    """``owner_limit`` режет кэш, не пересчитывая тяжёлые агрегаты (§5.2.7)."""
    points, owners = _sample()
    calls = _install(monkeypatch, points, owners)
    full = cd.coverage_dashboard(owner_limit=None)  # miss (computes)
    limited = cd.coverage_dashboard(owner_limit=1)  # hit → slice only
    assert calls == {"timeline": 1, "owners": 1}  # no recompute for the slice
    # worst offender first (pyro, gap_count=5), capped to one row
    assert [o["owner"] for o in limited["by_owner"]] == ["pyro"]
    assert [o["owner"] for o in full["by_owner"]] == ["pyro", "hydro", "unassigned"]
    # totals are over the full owner list, unaffected by the slice
    assert limited["summary"]["gaps_total"] == full["summary"]["gaps_total"] == 8
    assert limited["summary"]["owners"] == 3
    assert limited["summary"]["shown_owners"] == 1
    assert limited["summary"]["unassigned_gaps"] == 1


def test_timeline_derivation_unchanged(monkeypatch) -> None:
    """Производные поля таймлайна считаются как раньше поверх кэша (§15.5)."""
    points, owners = _sample()
    _install(monkeypatch, points, owners)
    resp = cd.coverage_dashboard(owner_limit=None)
    tl = resp["timeline"]
    assert [p["year"] for p in tl] == [2020, 2021]
    assert tl[0]["coverage_ratio"] == round(4 / (4 + 1), 4)  # 0.8
    assert tl[1]["coverage_ratio"] == 0.0  # 0 measurements
    assert resp["summary"] == {
        "years": 2,
        "papers": 4,
        "measurements": 4,
        "gaps_dated": 3,
        "gaps_total": 8,
        "owners": 3,
        "unassigned_gaps": 1,
        "shown_owners": 3,
    }


def test_ttl_expiry_triggers_recompute(monkeypatch) -> None:
    """По истечении TTL агрегаты пересчитываются / stale entry refreshed (§15.5)."""
    points, owners = _sample()
    calls = _install(monkeypatch, points, owners)
    monkeypatch.setattr(cd, "_CACHE_TTL_SECONDS", 0.0)  # entries expire immediately
    cd.coverage_dashboard(owner_limit=None)
    cd.coverage_dashboard(owner_limit=None)
    assert calls["timeline"] == 2 and calls["owners"] == 2
