"""Tests for :mod:`kg_common.sensor_spec` — сенсоры (§9.9)."""

from __future__ import annotations

import pytest

from kg_common.sensor_spec import KINDS, SensorSpec, should_trigger


def test_file_sensor_triggers_on_new_file() -> None:
    spec = SensorSpec(name="drop", kind="file", config={"last_seen": "a.csv"})
    assert should_trigger(spec, {"latest": "b.csv"}) is True
    assert should_trigger(spec, {"latest": "a.csv"}) is False
    assert should_trigger(spec, {"latest": ""}) is False


def test_interval_sensor_triggers_on_elapsed() -> None:
    spec = SensorSpec(name="poll", kind="interval", config={"last_run": 100, "interval": 60})
    assert should_trigger(spec, {"now": 160}) is True  # exactly elapsed
    assert should_trigger(spec, {"now": 200}) is True
    assert should_trigger(spec, {"now": 159}) is False  # one short


def test_db_sensor_triggers_on_advanced_cursor() -> None:
    spec = SensorSpec(name="cdc", kind="db", config={"last_cursor": 42})
    assert should_trigger(spec, {"cursor": 43}) is True
    assert should_trigger(spec, {"cursor": 42}) is False
    assert should_trigger(spec, {"cursor": 41}) is False


def test_disabled_never_triggers() -> None:
    spec = SensorSpec(name="off", kind="file", config={"last_seen": "a"}, enabled=False)
    assert should_trigger(spec, {"latest": "b"}) is False


def test_config_preserved_and_isolated() -> None:
    raw = {"last_seen": "a.csv", "extra": 7}
    spec = SensorSpec(name="drop", kind="file", config=raw)
    assert spec.config["last_seen"] == "a.csv"
    assert spec.config["extra"] == 7
    raw["last_seen"] = "mutated"  # caller mutation must not leak in
    assert spec.config["last_seen"] == "a.csv"


def test_as_dict() -> None:
    spec = SensorSpec(name="poll", kind="interval", config={"interval": 30}, enabled=True)
    assert spec.as_dict() == {
        "name": "poll",
        "kind": "interval",
        "config": {"interval": 30},
        "enabled": True,
    }


def test_from_dict_roundtrip() -> None:
    payload = {
        "name": "cdc",
        "kind": "db",
        "config": {"last_cursor": 5},
        "enabled": False,
    }
    spec = SensorSpec.from_dict(payload)
    assert spec.name == "cdc"
    assert spec.kind == "db"
    assert spec.config["last_cursor"] == 5
    assert spec.enabled is False
    assert spec.as_dict() == payload


def test_from_dict_defaults_enabled_true() -> None:
    spec = SensorSpec.from_dict({"name": "n", "kind": "file"})
    assert spec.enabled is True
    assert dict(spec.config) == {}


def test_unknown_kind_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        SensorSpec(name="bad", kind="socket")


def test_kinds_constant_is_canonical() -> None:
    assert KINDS == ("file", "interval", "db")
