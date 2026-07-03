"""Tests for the ExternalRef node DTO + payload-hash idempotency (§20.3)."""

from __future__ import annotations

import hashlib
import json

import pytest

from kg_schema.external_ref import (
    ALLOWED_SYSTEMS,
    ExternalRef,
    external_ref_key,
    is_changed,
    make_external_ref,
)


def test_allowed_systems_membership() -> None:
    assert (
        frozenset({"elabftw", "openbis", "materials_project", "matkg", "matscholar", "propnet"})
        == ALLOWED_SYSTEMS
    )


def test_external_ref_key_format() -> None:
    assert external_ref_key("materials_project", "mp-149") == "materials_project:mp-149"


def test_make_external_ref_id_prefix() -> None:
    assert make_external_ref("elabftw", "exp-1").id.startswith("extref:")


def test_make_external_ref_id_deterministic_hash() -> None:
    key = external_ref_key("elabftw", "exp-1")
    expected = "extref:" + hashlib.sha1(key.encode()).hexdigest()[:16]
    assert make_external_ref("elabftw", "exp-1").id == expected


def test_unknown_system_raises() -> None:
    with pytest.raises(ValueError):
        make_external_ref("foo", "x")


def test_payload_hash_deterministic() -> None:
    a = make_external_ref("matkg", "t", payload={"a": 1})
    b = make_external_ref("matkg", "t", payload={"a": 1})
    assert a.payload_hash == b.payload_hash


def test_payload_hash_key_order_insensitive() -> None:
    a = make_external_ref("matkg", "t", payload={"a": 1, "b": 2})
    b = make_external_ref("matkg", "t", payload={"b": 2, "a": 1})
    assert a.payload_hash == b.payload_hash


def test_payload_hash_expected_value() -> None:
    canonical = json.dumps({"a": 1}, sort_keys=True)
    expected = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    assert make_external_ref("matkg", "t", payload={"a": 1}).payload_hash == expected


def test_different_payload_different_hash() -> None:
    a = make_external_ref("matkg", "t", payload={"a": 1})
    b = make_external_ref("matkg", "t", payload={"a": 2})
    assert a.payload_hash != b.payload_hash


def test_empty_and_none_payload_equal() -> None:
    none_ref = make_external_ref("propnet", "p", payload=None)
    empty_ref = make_external_ref("propnet", "p", payload={})
    assert none_ref.payload_hash == empty_ref.payload_hash


def test_is_changed() -> None:
    ref_from_a = make_external_ref("matkg", "t", payload={"a": 1})
    assert is_changed(ref_from_a, {"a": 1}) is False
    assert is_changed(ref_from_a, {"a": 2}) is True


def test_as_dict_shape() -> None:
    ref = make_external_ref(
        "openbis",
        "OBJ-1",
        external_url="https://openbis.example/OBJ-1",
        system_version="20.10.0",
        fetched_at="2026-07-03T00:00:00+00:00",
        payload={"x": 1},
    )
    d = ref.as_dict()
    assert len(d) == 7
    assert set(d) == {
        "id",
        "system",
        "external_id",
        "external_url",
        "system_version",
        "fetched_at",
        "payload_hash",
    }
    assert d["system"] in ALLOWED_SYSTEMS


def test_as_dict_round_trips() -> None:
    ref = make_external_ref("matscholar", "doc-9", payload={"k": "v"})
    assert ExternalRef(**ref.as_dict()) == ref


def test_frozen_dataclass_immutable() -> None:
    ref = make_external_ref("elabftw", "exp-2")
    with pytest.raises((AttributeError, TypeError)):
        ref.system = "openbis"  # type: ignore[misc]
