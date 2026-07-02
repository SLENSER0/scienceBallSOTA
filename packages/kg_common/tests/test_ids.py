"""Deterministic ID / canonical-key tests (§3.8)."""

from __future__ import annotations

from kg_common.ids import canonical_key, make_id, regime_id, uuid5_id


def test_canonical_key_normalizes() -> None:
    assert canonical_key("Al-Cu 2024") == canonical_key("al  cu   2024")
    assert canonical_key("  Электроэкстракция  ") == "электроэкстракция"
    assert canonical_key("ПВП / flash smelting") == "пвп flash smelting"


def test_make_id_deterministic_and_prefixed() -> None:
    a = make_id("Material", "Al-Cu 2024")
    b = make_id("Material", "al cu 2024")
    assert a == b
    assert a.startswith("material:")
    assert make_id("Property", "Hardness") == "property:hardness"


def test_make_id_order_independent_via_hash() -> None:
    assert regime_id("aging", 180, 2, "air") == regime_id("aging", 180, 2, "air")
    assert regime_id("aging", 180, 2, "air") != regime_id("aging", 200, 2, "air")


def test_uuid5_stable() -> None:
    x = uuid5_id("Evidence", "doc:1", (10, 20), "run:1")
    y = uuid5_id("Evidence", "doc:1", (10, 20), "run:1")
    assert x == y and x.startswith("ev:")
