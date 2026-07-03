"""Tests for the GraphRAG mode guard (§11.12)."""

from __future__ import annotations

from kg_retrievers.graphrag_mode_guard import (
    ModeDecision,
    decide_mode,
    is_structured_query,
)


def test_enabled_global_built_routes_to_graphrag() -> None:
    """enabled + global intent + built build -> graphrag primary, no warning."""
    d = decide_mode(
        "общий обзор направления по титановым сплавам",
        enabled=True,
        build_status="built",
        is_global_intent=True,
    )
    assert d.mode == "graphrag"
    assert d.primary is True
    assert d.warning is None
    assert d.fallback is None


def test_disabled_falls_back_to_hybrid_with_warning() -> None:
    """enabled=False + global -> hybrid, fallback='hybrid', warning set."""
    d = decide_mode(
        "общий обзор темы",
        enabled=False,
        build_status="built",
        is_global_intent=True,
    )
    assert d.mode == "hybrid"
    assert d.primary is False
    assert d.fallback == "hybrid"
    assert d.warning is not None
    assert "disabled" in d.warning.lower()


def test_narrow_intent_never_routes_to_graphrag() -> None:
    """is_global_intent=False -> never graphrag even when enabled + built."""
    d = decide_mode(
        "yield strength of Ti-6Al-4V",
        enabled=True,
        build_status="built",
        is_global_intent=False,
    )
    assert d.mode == "hybrid"
    assert d.primary is False
    assert d.fallback == "hybrid"


def test_build_failed_falls_back_with_build_warning() -> None:
    """build_status='failed' -> hybrid; warning mentions the build."""
    d = decide_mode(
        "общий обзор темы",
        enabled=True,
        build_status="failed",
        is_global_intent=True,
    )
    assert d.mode == "hybrid"
    assert d.primary is False
    assert d.fallback == "hybrid"
    assert d.warning is not None
    assert "build" in d.warning.lower()


def test_build_status_none_falls_back_to_hybrid() -> None:
    """build_status=None -> hybrid with a warning."""
    d = decide_mode(
        "общий обзор темы",
        enabled=True,
        build_status=None,
        is_global_intent=True,
    )
    assert d.mode == "hybrid"
    assert d.primary is False
    assert d.fallback == "hybrid"
    assert d.warning is not None
    assert "build" in d.warning.lower()


def test_is_structured_query_detects_numeric_and_rejects_broad() -> None:
    """Numeric material-property shape True; broad survey question False."""
    assert is_structured_query("hardness 320 MPa of Al after aging") is True
    assert is_structured_query("общий обзор темы") is False


def test_as_dict_keys_are_exact() -> None:
    """as_dict exposes exactly {mode, primary, fallback, warning, reason}."""
    d = decide_mode(
        "общий обзор темы",
        enabled=True,
        build_status="built",
        is_global_intent=True,
    )
    assert set(d.as_dict().keys()) == {"mode", "primary", "fallback", "warning", "reason"}


def test_structured_query_forces_hybrid_even_when_flagged_global() -> None:
    """A numeric structured query is narrow -> hybrid even if is_global_intent."""
    d = decide_mode(
        "hardness 320 MPa of Al after aging",
        enabled=True,
        build_status="built",
        is_global_intent=True,
    )
    assert d.mode == "hybrid"
    assert d.primary is False


def test_mode_decision_is_frozen() -> None:
    """ModeDecision is immutable (frozen dataclass)."""
    d = ModeDecision("hybrid", False, "hybrid", None, "reason")
    try:
        d.mode = "graphrag"  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:  # pragma: no cover
        raise AssertionError("ModeDecision must be frozen")
