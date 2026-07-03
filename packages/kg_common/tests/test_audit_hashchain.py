"""Tests for the tamper-evident audit hash-chain (§10.8)."""

from __future__ import annotations

from dataclasses import replace

from kg_common.audit_hashchain import (
    GENESIS_HASH,
    AuditRecord,
    append,
    compute_hash,
    verify_chain,
)


def _build_chain() -> list[AuditRecord]:
    """A clean three-record chain used by several tests."""
    chain: list[AuditRecord] = []
    chain.append(append(chain, "alice", "create", "node", "1", {"k": 1}))
    chain.append(append(chain, "bob", "update", "node", "1", {"k": 2}))
    chain.append(append(chain, "carol", "delete", "node", "1", {"k": 3}))
    return chain


def test_first_append_links_to_genesis() -> None:
    chain: list[AuditRecord] = []
    r0 = append(chain, "alice", "create", "node", "1", {"x": 1})
    assert r0.prev_hash == GENESIS_HASH
    assert r0.seq == 0


def test_second_append_links_to_first_hash() -> None:
    chain: list[AuditRecord] = []
    r1 = append(chain, "alice", "create", "node", "1", {"x": 1})
    chain.append(r1)
    r2 = append(chain, "bob", "update", "node", "1", {"x": 2})
    assert r2.prev_hash == r1.hash
    assert r2.seq == 1


def test_verify_clean_chain() -> None:
    assert verify_chain(_build_chain()) == (True, -1)


def test_verify_detects_tampered_record() -> None:
    chain = _build_chain()
    # Rebuild record 1 with a mutated payload but leave its (now-wrong) hash.
    tampered = replace(chain[1], payload={"k": 999})
    chain[1] = tampered
    assert verify_chain(chain) == (False, 1)


def test_compute_hash_deterministic() -> None:
    first = compute_hash(GENESIS_HASH, "alice", "create", "node", "1", {"a": 1, "b": 2})
    second = compute_hash(GENESIS_HASH, "alice", "create", "node", "1", {"b": 2, "a": 1})
    # Canonical encoding: identical values (even reordered) hash identically.
    assert first == second


def test_compute_hash_differs_on_target_id() -> None:
    h1 = compute_hash(GENESIS_HASH, "alice", "create", "node", "1", {})
    h2 = compute_hash(GENESIS_HASH, "alice", "create", "node", "2", {})
    assert h1 != h2


def test_as_dict_round_trips_hash() -> None:
    chain: list[AuditRecord] = []
    r0 = append(chain, "alice", "create", "node", "1", {"x": 1})
    d = r0.as_dict()
    assert d["hash"] == r0.hash
    assert d["prev_hash"] == GENESIS_HASH
    assert d["seq"] == 0
    assert d["payload"] == {"x": 1}


def test_seq_increments_monotonically() -> None:
    chain: list[AuditRecord] = []
    for i in range(5):
        chain.append(append(chain, "alice", "act", "node", str(i), {"i": i}))
    assert [r.seq for r in chain] == [0, 1, 2, 3, 4]


def test_hash_is_sha256_hex() -> None:
    r = append([], "alice", "create", "node", "1", {})
    assert len(r.hash) == 64
    assert all(c in "0123456789abcdef" for c in r.hash)


def test_tamper_in_first_record_reports_seq_zero() -> None:
    chain = _build_chain()
    chain[0] = replace(chain[0], actor_id="mallory")
    assert verify_chain(chain) == (False, 0)


def test_verify_empty_chain_is_intact() -> None:
    assert verify_chain([]) == (True, -1)
