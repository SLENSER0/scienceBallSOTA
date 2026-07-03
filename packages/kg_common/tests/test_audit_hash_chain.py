"""Tests for the audit hash-chain — тесты цепочки хэшей аудита (§10.8)."""

from __future__ import annotations

import dataclasses
import hashlib
import json

from kg_common.audit_hash_chain import (
    GENESIS_PREV,
    ChainedRecord,
    append_record,
    build_chain,
    find_break,
    hash_payload,
    verify_chain,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_genesis_prev_is_64_zero_hex_chars() -> None:
    assert GENESIS_PREV == "0" * 64
    assert len(GENESIS_PREV) == 64


def test_first_record_prev_hash_is_genesis() -> None:
    chain = build_chain([{"a": 1}])
    assert chain[0].prev_hash == GENESIS_PREV


def test_hash_payload_is_key_order_independent() -> None:
    assert hash_payload({"a": 1, "b": 2}) == hash_payload({"b": 2, "a": 1})


def test_hash_payload_matches_manual_canonical_sha256() -> None:
    payload = {"b": 2, "a": 1}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert canonical == '{"a":1,"b":2}'
    assert hash_payload(payload) == _sha('{"a":1,"b":2}')


def test_different_payloads_hash_differently() -> None:
    assert hash_payload({"x": 1}) != hash_payload({"x": 2})


def test_build_chain_links_and_verifies() -> None:
    chain = build_chain([{"x": 1}, {"x": 2}])
    assert verify_chain(chain) is True
    assert find_break(chain) is None
    assert chain[1].prev_hash == chain[0].hash


def test_link_hash_matches_manual_computation() -> None:
    chain = build_chain([{"x": 1}, {"x": 2}])
    first = chain[0]
    assert first.prev_hash == GENESIS_PREV
    assert first.payload_hash == hash_payload({"x": 1})
    assert first.hash == _sha(GENESIS_PREV + hash_payload({"x": 1}))
    second = chain[1]
    assert second.hash == _sha(first.hash + hash_payload({"x": 2}))


def test_indices_are_sequential() -> None:
    chain = build_chain([{"a": 1}, {"b": 2}, {"c": 3}])
    assert [r.index for r in chain] == [0, 1, 2]


def test_build_chain_length() -> None:
    assert len(build_chain([{"a": 1}, {"b": 2}, {"c": 3}])) == 3


def test_empty_chain_is_valid() -> None:
    assert build_chain([]) == []
    assert verify_chain([]) is True
    assert find_break([]) is None


def test_tampering_first_record_breaks_chain() -> None:
    chain = build_chain([{"x": 1}, {"x": 2}])
    tampered_first = dataclasses.replace(chain[0], payload_hash=hash_payload({"x": 99}))
    tampered = [tampered_first, chain[1]]
    assert verify_chain(tampered) is False
    assert find_break(tampered) == 0


def test_tampering_middle_record_reported_at_that_index() -> None:
    chain = build_chain([{"a": 1}, {"b": 2}, {"c": 3}])
    # Break the link between record 0 and record 1 by rewriting record 1's prev_hash.
    tampered_second = dataclasses.replace(chain[1], prev_hash=GENESIS_PREV)
    tampered = [chain[0], tampered_second, chain[2]]
    assert verify_chain(tampered) is False
    assert find_break(tampered) == 1


def test_append_record_does_not_mutate_chain() -> None:
    chain = build_chain([{"x": 1}])
    before = list(chain)
    nxt = append_record(chain, {"x": 2})
    assert chain == before
    assert nxt.index == 1
    assert nxt.prev_hash == chain[0].hash


def test_append_record_on_empty_chain_uses_genesis() -> None:
    rec = append_record([], {"a": 1})
    assert rec.index == 0
    assert rec.prev_hash == GENESIS_PREV
    assert rec.hash == _sha(GENESIS_PREV + hash_payload({"a": 1}))


def test_as_dict_shape() -> None:
    rec = build_chain([{"a": 1}])[0]
    assert rec.as_dict() == {
        "index": 0,
        "payload_hash": rec.payload_hash,
        "prev_hash": rec.prev_hash,
        "hash": rec.hash,
    }


def test_chained_record_is_frozen() -> None:
    rec = build_chain([{"a": 1}])[0]
    assert isinstance(rec, ChainedRecord)
    try:
        rec.hash = "x"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("ChainedRecord should be frozen")
