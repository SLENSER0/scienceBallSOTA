"""Tests for §13.10 numeric tolerance relaxation on verifier-retry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import orjson
import pytest
from agent_service.numeric_constraint_relax import (
    DEFAULT_TOLERANCES,
    TOLERANCE_KEYS,
    RelaxedConstraints,
    relax,
)


def test_attempt_zero_keeps_base_tolerances() -> None:
    """Assertion (1): attempt 0 leaves tolerances at their base (factor**0 == 1)."""
    out = relax({"temperature_c": 200}, 0, factor=1.5)
    assert out.tolerances["temperature_tolerance"] == DEFAULT_TOLERANCES["temperature_tolerance"]
    assert out.attempt == 0


def test_attempt_one_widens_by_factor() -> None:
    """Assertion (2): attempt 1, base 5, factor 1.5 -> 7.5."""
    out = relax({"temperature_c": 200}, 1, factor=1.5, base={"temperature_tolerance": 5.0})
    assert out.tolerances["temperature_tolerance"] == 7.5


def test_attempt_two_widens_geometrically() -> None:
    """Assertion (3): attempt 2 -> 5 * 1.5**2 == 11.25."""
    out = relax({"temperature_c": 200}, 2, factor=1.5, base={"temperature_tolerance": 5.0})
    assert out.tolerances["temperature_tolerance"] == 11.25


def test_only_present_keys_are_widened() -> None:
    """Assertion (4): only keys present in constraints appear in widened."""
    out = relax({"temperature_c": 200}, 1)
    assert out.widened == ("temperature_c",)
    assert "time_h" not in out.widened
    out_both = relax({"temperature_c": 200, "time_h": 4}, 1)
    assert set(out_both.widened) == {"temperature_c", "time_h"}
    assert "time_tolerance" in out_both.tolerances


def test_unmapped_constraint_is_ignored() -> None:
    """Assertion (5): a constraint without a mapped tolerance key is ignored."""
    out = relax({"pressure_mpa": 10}, 1)
    assert out.widened == ()
    assert out.tolerances == {}


def test_input_constraints_not_mutated() -> None:
    """Assertion (6): constraints dict is copied, not mutated (input unchanged)."""
    src = {"temperature_c": 200}
    out = relax(src, 3)
    assert src == {"temperature_c": 200}
    assert out.constraints is not src
    assert out.constraints == {"temperature_c": 200}


def test_empty_constraints_widen_nothing() -> None:
    """Assertion (7): empty constraints -> widened == ()."""
    out = relax({}, 5)
    assert out.widened == ()
    assert out.tolerances == {}


def test_as_dict_orjson_roundtrips() -> None:
    """Assertion (8): as_dict is orjson-serialisable and round-trips."""
    out = relax({"temperature_c": 200, "time_h": 4}, 1, factor=1.5)
    payload = out.as_dict()
    raw = orjson.dumps(payload)
    loaded = orjson.loads(raw)
    assert loaded == payload
    assert loaded["widened"] == ["temperature_c", "time_h"]
    assert loaded["attempt"] == 1


def test_constraint_values_unchanged_only_tolerances_grow() -> None:
    """Values stay put across attempts; only tolerances widen (§13.10 invariant)."""
    a0 = relax({"temperature_c": 200}, 0)
    a2 = relax({"temperature_c": 200}, 2)
    assert a0.constraints == a2.constraints == {"temperature_c": 200}
    assert a2.tolerances["temperature_tolerance"] > a0.tolerances["temperature_tolerance"]


def test_tolerance_keys_mapping_shape() -> None:
    """TOLERANCE_KEYS maps the two §13.10 numeric keys to their tolerance keys."""
    assert TOLERANCE_KEYS == {
        "temperature_c": "temperature_tolerance",
        "time_h": "time_tolerance",
    }


def test_relaxed_constraints_is_frozen() -> None:
    """RelaxedConstraints is a frozen dataclass (immutable result)."""
    out = relax({"temperature_c": 200}, 1)
    assert isinstance(out, RelaxedConstraints)
    with pytest.raises(FrozenInstanceError):
        out.attempt = 9  # type: ignore[misc]
