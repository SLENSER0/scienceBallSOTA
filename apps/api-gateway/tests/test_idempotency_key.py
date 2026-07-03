"""Tests for Idempotency-Key replay/conflict handling (§14.10/14.12).

Проверяет валидацию ключа, детерминированный отпечаток запроса и три исхода
регистрации (stored/replay/conflict) согласно §14.10/§14.12.

Exercises key validation, the deterministic request fingerprint, and the three
:meth:`IdempotencyStore.register` outcomes (stored/replay/conflict).
"""

from __future__ import annotations

from api_gateway.idempotency_key import (
    IdempotencyRecord,
    IdempotencyStore,
    fingerprint,
    is_valid_key,
)


def test_is_valid_key_rules() -> None:
    """Пустой/длинный/непечатный отклоняются, обычный принимается (§14.10)."""
    assert is_valid_key("") is False
    assert is_valid_key("abc") is True
    assert is_valid_key("x" * 201) is False
    assert is_valid_key("x" * 200) is True
    assert is_valid_key("with space ok") is True
    assert is_valid_key("tab\tbad") is False
    assert is_valid_key("unicode-é") is False


def test_fingerprint_is_deterministic_and_body_sensitive() -> None:
    """Один и тот же запрос → тот же отпечаток; иное тело → иной (§14.10)."""
    assert fingerprint("POST", "/x", b"a") == fingerprint("POST", "/x", b"a")
    assert fingerprint("POST", "/x", b"a") != fingerprint("POST", "/x", b"b")
    assert fingerprint("POST", "/x", b"a") != fingerprint("POST", "/y", b"a")
    assert fingerprint("POST", "/x", b"a") != fingerprint("PUT", "/x", b"a")
    # sha256 hex digest is 64 lowercase hex chars.
    fp = fingerprint("POST", "/x", b"a")
    assert len(fp) == 64
    assert all(ch in "0123456789abcdef" for ch in fp)


def test_register_stored_then_replay_then_conflict() -> None:
    """Первый вызов stored, повтор — replay, иной отпечаток — conflict (§14.10)."""
    store = IdempotencyStore()
    fp = fingerprint("POST", "/x", b"a")
    other_fp = fingerprint("POST", "/x", b"b")

    outcome, record = store.register("k", fp, {"r": 1})
    assert outcome == "stored"
    assert record.response == {"r": 1}

    # Same key + same fingerprint → replay returns the ORIGINAL response.
    outcome, record = store.register("k", fp, {"r": 9})
    assert outcome == "replay"
    assert record.response == {"r": 1}

    # Same key + different fingerprint → conflict, original record returned.
    outcome, record = store.register("k", other_fp, {"r": 1})
    assert outcome == "conflict"
    assert record.response == {"r": 1}
    assert record.request_fingerprint == fp


def test_distinct_keys_are_independent() -> None:
    """Разные ключи хранятся независимо / distinct keys stored apart (§14.10)."""
    store = IdempotencyStore()
    fp1 = fingerprint("POST", "/a", b"1")
    fp2 = fingerprint("POST", "/b", b"2")
    assert store.register("k1", fp1, {"n": 1})[0] == "stored"
    assert store.register("k2", fp2, {"n": 2})[0] == "stored"
    assert store.register("k1", fp1, {"n": 9})[0] == "replay"
    assert store.get("k2") is not None
    assert store.get("missing") is None


def test_record_as_dict_round_trip() -> None:
    """as_dict() отдаёт все поля записи / record fields exposed (§14.10)."""
    store = IdempotencyStore()
    fp = fingerprint("POST", "/x", b"a")
    _, record = store.register("k", fp, {"r": 1})
    data = record.as_dict()
    assert data["key"] == "k"
    assert data["request_fingerprint"] == fp
    assert data["response"] == {"r": 1}
    assert isinstance(data["created_at"], str) and data["created_at"]


def test_record_is_frozen() -> None:
    """Запись неизменяема / IdempotencyRecord is frozen (§14.10)."""
    record = IdempotencyRecord("k", "fp", {"r": 1}, "2026-07-03T00:00:00+00:00")
    try:
        record.key = "other"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("IdempotencyRecord should be immutable (frozen)")
