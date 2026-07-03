"""Tests for the GraphRAG offline capability probe (§11.14)."""

from __future__ import annotations

from kg_retrievers.graphrag_offline_probe import (
    GraphRagCapability,
    assert_modes_independent,
    probe_capability,
)

_BUILD = {"build_id": "b-1", "status": "built"}


def test_all_present_available_no_reasons() -> None:
    cap = probe_capability(package_present=True, active_build=_BUILD, flag_enabled=True)
    assert cap.available is True
    assert cap.has_active_build is True
    assert cap.reasons == []
    assert cap.degraded_modes == ("A", "B", "D")


def test_package_missing_unavailable_with_reason() -> None:
    cap = probe_capability(package_present=False, active_build=_BUILD, flag_enabled=True)
    assert cap.available is False
    assert cap.has_active_build is True
    assert "graphrag package missing" in cap.reasons


def test_no_active_build_unavailable_and_flag() -> None:
    cap = probe_capability(package_present=True, active_build=None, flag_enabled=True)
    assert cap.available is False
    assert cap.has_active_build is False
    assert "no active graphrag build" in cap.reasons


def test_flag_disabled_unavailable_with_flag_reason() -> None:
    cap = probe_capability(package_present=True, active_build=_BUILD, flag_enabled=False)
    assert cap.available is False
    assert cap.has_active_build is True
    assert "graphrag feature flag disabled" in cap.reasons


def test_all_missing_collects_all_reasons() -> None:
    cap = probe_capability(package_present=False, active_build=None, flag_enabled=False)
    assert cap.available is False
    assert cap.has_active_build is False
    assert cap.reasons == [
        "graphrag package missing",
        "no active graphrag build",
        "graphrag feature flag disabled",
    ]


def test_degraded_modes_present_even_when_unavailable() -> None:
    cap = probe_capability(package_present=False, active_build=None, flag_enabled=False)
    assert cap.available is False
    assert "A" in cap.degraded_modes
    assert "B" in cap.degraded_modes
    assert "D" in cap.degraded_modes


def test_degraded_modes_present_when_available() -> None:
    cap = probe_capability(package_present=True, active_build=_BUILD, flag_enabled=True)
    assert cap.available is True
    assert set(cap.degraded_modes) == {"A", "B", "D"}


def test_assert_modes_independent_true_when_available() -> None:
    cap = probe_capability(package_present=True, active_build=_BUILD, flag_enabled=True)
    assert assert_modes_independent(cap) is True


def test_assert_modes_independent_true_when_unavailable() -> None:
    cap = probe_capability(package_present=False, active_build=None, flag_enabled=False)
    assert assert_modes_independent(cap) is True


def test_assert_modes_independent_false_when_mode_absent() -> None:
    broken = GraphRagCapability(
        available=False,
        has_active_build=False,
        reasons=["x"],
        degraded_modes=("A", "B"),
    )
    assert assert_modes_independent(broken) is False


def test_as_dict_shape_and_degraded_modes_list() -> None:
    cap = probe_capability(package_present=True, active_build=_BUILD, flag_enabled=True)
    d = cap.as_dict()
    assert d == {
        "available": True,
        "has_active_build": True,
        "reasons": [],
        "degraded_modes": ["A", "B", "D"],
    }
    assert list(d["degraded_modes"]) == ["A", "B", "D"]


def test_as_dict_reasons_copied_not_shared() -> None:
    cap = probe_capability(package_present=False, active_build=_BUILD, flag_enabled=True)
    d = cap.as_dict()
    d["reasons"].append("mutated")
    assert cap.reasons == ["graphrag package missing"]


def test_frozen_dataclass_immutable() -> None:
    cap = probe_capability(package_present=True, active_build=_BUILD, flag_enabled=True)
    import dataclasses

    try:
        cap.available = False  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("expected FrozenInstanceError")
