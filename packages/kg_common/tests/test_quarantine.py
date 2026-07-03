"""Tests for :mod:`kg_common.quarantine` — единый формат «карантина» (§20.11)."""

from __future__ import annotations

import hashlib
import json

from kg_common.quarantine import (
    QuarantineRecord,
    is_duplicate,
    make_quarantine,
    mark_retry,
)


def test_record_id_prefix_and_starts_at_zero() -> None:
    rec = make_quarantine("elabftw", "schema_validation", "ValidationError", "bad", {"a": 1})
    assert rec.record_id.startswith("quar:")
    assert rec.retry_count == 0


def test_payload_hash_matches_manual_sha256() -> None:
    payload = {"b": 2, "a": 1}
    rec = make_quarantine("s", "st", "E", "m", payload)
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    assert rec.payload_hash == expected


def test_record_id_matches_manual_sha1() -> None:
    rec = make_quarantine("s", "st", "E", "m", {"a": 1})
    key = f"s|st|{rec.payload_hash}"
    expected = "quar:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    assert rec.record_id == expected


def test_payload_hash_deterministic() -> None:
    a = make_quarantine("s", "st", "E", "m", {"a": 1})
    b = make_quarantine("s", "st", "E", "m", {"a": 1})
    assert a.payload_hash == b.payload_hash
    assert a.record_id == b.record_id


def test_payload_hash_key_order_independent() -> None:
    a = make_quarantine("s", "st", "E", "m", {"a": 1, "b": 2})
    b = make_quarantine("s", "st", "E", "m", {"b": 2, "a": 1})
    assert a.payload_hash == b.payload_hash


def test_mark_retry_increments() -> None:
    rec = make_quarantine("s", "st", "E", "m", {"a": 1})
    once = mark_retry(rec)
    assert once.retry_count == rec.retry_count + 1
    assert mark_retry(once).retry_count == 2
    # original is unchanged (frozen / functional update)
    assert rec.retry_count == 0


def test_mark_retry_preserves_identity_fields() -> None:
    rec = make_quarantine("s", "st", "E", "m", {"a": 1})
    once = mark_retry(rec)
    assert once.record_id == rec.record_id
    assert once.payload_hash == rec.payload_hash
    assert once.source == rec.source


def test_is_duplicate_self() -> None:
    rec = make_quarantine("s", "st", "E", "m", {"a": 1})
    assert is_duplicate(rec, rec) is True


def test_is_duplicate_ignores_retry_and_message() -> None:
    rec = make_quarantine("s", "st", "E", "m", {"a": 1})
    other = make_quarantine("s", "st", "OtherErr", "different", {"a": 1})
    assert is_duplicate(rec, mark_retry(other)) is True


def test_different_payload_distinct() -> None:
    a = make_quarantine("s", "st", "E", "m", {"a": 1})
    b = make_quarantine("s", "st", "E", "m", {"a": 2})
    assert a.record_id != b.record_id
    assert a.payload_hash != b.payload_hash
    assert is_duplicate(a, b) is False


def test_different_source_or_stage_not_duplicate() -> None:
    base = make_quarantine("s", "st", "E", "m", {"a": 1})
    other_source = make_quarantine("s2", "st", "E", "m", {"a": 1})
    other_stage = make_quarantine("s", "st2", "E", "m", {"a": 1})
    assert is_duplicate(base, other_source) is False
    assert is_duplicate(base, other_stage) is False
    assert base.record_id != other_source.record_id
    assert base.record_id != other_stage.record_id


def test_as_dict_has_eight_keys() -> None:
    rec = make_quarantine(
        "elabftw",
        "schema_validation",
        "ValidationError",
        "bad",
        {"a": 1},
        created_at="2026-07-03T00:00:00Z",
    )
    d = rec.as_dict()
    assert len(d) == 8
    assert set(d) == {
        "record_id",
        "source",
        "stage",
        "error_type",
        "message",
        "payload_hash",
        "retry_count",
        "created_at",
    }
    assert d["created_at"] == "2026-07-03T00:00:00Z"
    assert d["source"] == "elabftw"


def test_created_at_defaults_empty() -> None:
    rec = make_quarantine("s", "st", "E", "m", {"a": 1})
    assert rec.created_at == ""


def test_is_frozen() -> None:
    rec = make_quarantine("s", "st", "E", "m", {"a": 1})
    assert isinstance(rec, QuarantineRecord)
    try:
        rec.retry_count = 5  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("QuarantineRecord must be frozen")
