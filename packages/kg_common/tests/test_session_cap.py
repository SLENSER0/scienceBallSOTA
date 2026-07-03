"""Tests for per-user session cap with oldest-session eviction (§19.2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from kg_common.security.session_cap import (
    OpenResult,
    SessionCapConfig,
    SessionRecord,
    SessionRegistry,
)


def _reg(max_sessions: int = 2) -> SessionRegistry:
    return SessionRegistry(SessionCapConfig(max_sessions=max_sessions))


def test_third_session_evicts_oldest() -> None:
    # Assertion (1): max=2, open s1@1, s2@2, s3@3 -> evicted ('s1',), count 2.
    reg = _reg(2)
    reg.open_session("u", "s1", now=1.0)
    reg.open_session("u", "s2", now=2.0)
    result = reg.open_session("u", "s3", now=3.0)
    assert result.evicted == ("s1",)
    assert result.active_count == 2


def test_active_sessions_sorted_after_eviction() -> None:
    # Assertion (2): active_sessions returns s2, s3 sorted by created_at.
    reg = _reg(2)
    reg.open_session("u", "s1", now=1.0)
    reg.open_session("u", "s2", now=2.0)
    reg.open_session("u", "s3", now=3.0)
    active = reg.active_sessions("u")
    assert [r.session_id for r in active] == ["s2", "s3"]
    assert [r.created_at for r in active] == [2.0, 3.0]


def test_close_existing_session() -> None:
    # Assertion (3): close_session('s2') is True and drops count to 1.
    reg = _reg(2)
    reg.open_session("u", "s2", now=2.0)
    reg.open_session("u", "s3", now=3.0)
    assert reg.close_session("s2") is True
    assert len(reg.active_sessions("u")) == 1
    assert reg.active_sessions("u")[0].session_id == "s3"


def test_close_unknown_session() -> None:
    # Assertion (4): close_session('nope') returns False.
    reg = _reg(2)
    assert reg.close_session("nope") is False


def test_reopen_does_not_double_count() -> None:
    # Assertion (5): re-opening an existing session_id keeps active_count.
    reg = _reg(2)
    reg.open_session("u", "s1", now=1.0)
    first = reg.open_session("u", "s2", now=2.0)
    assert first.active_count == 2
    again = reg.open_session("u", "s2", now=9.0)
    assert again.evicted == ()
    assert again.active_count == 2
    # Original created_at is preserved (not overwritten by the re-open).
    rec = {r.session_id: r for r in reg.active_sessions("u")}["s2"]
    assert rec.created_at == 2.0


def test_eviction_removes_lowest_created_at_first() -> None:
    # Assertion (6): eviction always removes lowest created_at first, even
    # when sessions were opened out of timestamp order.
    reg = _reg(2)
    reg.open_session("u", "sB", now=5.0)
    reg.open_session("u", "sA", now=1.0)  # older timestamp, inserted later
    result = reg.open_session("u", "sC", now=9.0)
    assert result.evicted == ("sA",)
    assert [r.session_id for r in reg.active_sessions("u")] == ["sB", "sC"]


def test_fresh_user_has_no_sessions() -> None:
    # Assertion (7): a fresh user's active_sessions is ().
    reg = _reg(2)
    assert reg.active_sessions("ghost") == ()


def test_open_result_as_dict() -> None:
    # Assertion (8): OpenResult.as_dict exposes evicted and active_count.
    reg = _reg(2)
    reg.open_session("u", "s1", now=1.0)
    reg.open_session("u", "s2", now=2.0)
    result = reg.open_session("u", "s3", now=3.0)
    d = result.as_dict()
    assert d["evicted"] == ["s1"]
    assert d["active_count"] == 2
    assert d["session_id"] == "s3"


def test_multi_eviction_when_over_by_many() -> None:
    # max=1: each new session evicts the single prior one.
    reg = _reg(1)
    reg.open_session("u", "s1", now=1.0)
    r2 = reg.open_session("u", "s2", now=2.0)
    assert r2.evicted == ("s1",)
    assert r2.active_count == 1


def test_per_user_isolation() -> None:
    # Sessions of other users are never evicted or counted.
    reg = _reg(2)
    reg.open_session("u", "u1", now=1.0)
    reg.open_session("v", "v1", now=1.0)
    reg.open_session("u", "u2", now=2.0)
    reg.open_session("u", "u3", now=3.0)  # evicts u1 only
    assert reg.active_sessions("v") == (
        SessionRecord(session_id="v1", user_id="v", created_at=1.0),
    )
    assert [r.session_id for r in reg.active_sessions("u")] == ["u2", "u3"]


def test_config_and_record_as_dict() -> None:
    cfg = SessionCapConfig(max_sessions=3)
    assert cfg.as_dict() == {"max_sessions": 3}
    rec = SessionRecord(session_id="s", user_id="u", created_at=4.5)
    assert rec.as_dict() == {"session_id": "s", "user_id": "u", "created_at": 4.5}


def test_frozen_dataclasses() -> None:
    result = OpenResult(session_id="s", evicted=(), active_count=0)
    for obj, field in (
        (SessionCapConfig(max_sessions=1), "max_sessions"),
        (SessionRecord(session_id="s", user_id="u", created_at=1.0), "session_id"),
        (result, "active_count"),
    ):
        try:
            setattr(obj, field, 99)
        except FrozenInstanceError:
            continue
        raise AssertionError(f"{type(obj).__name__} should be frozen")


def test_invalid_max_sessions() -> None:
    for bad in (0, -1):
        try:
            SessionCapConfig(max_sessions=bad)
        except ValueError:
            continue
        raise AssertionError("expected ValueError for max_sessions < 1")
