"""Tests for the GraphRAG fallback gate (§11.12)."""

from __future__ import annotations

from kg_retrievers.graphrag_fallback_gate import GateDecision, decide_graphrag


def test_all_clear_routes_to_graphrag() -> None:
    """enabled + built + broad -> use_graphrag True, mode_note set, warning None."""
    decision = decide_graphrag(enabled=True, build_status="built", is_broad_intent=True)
    assert decision.use_graphrag is True
    assert decision.mode_note == "обзорный ответ на основе community summaries"
    assert decision.warning is None
    assert decision.fallback_mode == "hybrid"


def test_disabled_falls_back_with_disabled_warning() -> None:
    """enabled False -> use_graphrag False, fallback_mode 'hybrid', warning mentions 'disabled'."""
    decision = decide_graphrag(enabled=False, build_status="built", is_broad_intent=True)
    assert decision.use_graphrag is False
    assert decision.fallback_mode == "hybrid"
    assert decision.warning is not None
    assert "disabled" in decision.warning
    assert decision.mode_note is None


def test_failed_build_has_no_active_build_warning() -> None:
    """build_status 'failed' -> False with 'no active build' warning."""
    decision = decide_graphrag(enabled=True, build_status="failed", is_broad_intent=True)
    assert decision.use_graphrag is False
    assert decision.warning == "no active build"
    assert decision.mode_note is None


def test_none_build_status_declines() -> None:
    """build_status None -> False (no active build)."""
    decision = decide_graphrag(enabled=True, build_status=None, is_broad_intent=True)
    assert decision.use_graphrag is False
    assert decision.warning == "no active build"


def test_narrow_query_declines_with_not_broad_warning() -> None:
    """broad False -> False with 'not a broad' warning."""
    decision = decide_graphrag(enabled=True, build_status="built", is_broad_intent=False)
    assert decision.use_graphrag is False
    assert decision.warning is not None
    assert "not a broad" in decision.warning
    assert decision.mode_note is None


def test_narrow_numeric_query_never_routed() -> None:
    """A narrow numeric query (is_broad_intent False) is never routed to graphrag."""
    decision = decide_graphrag(enabled=True, build_status="built", is_broad_intent=False)
    assert decision.use_graphrag is False


def test_as_dict_mode_note_none_on_fallback() -> None:
    """as_dict()['mode_note'] is None on fallback."""
    decision = decide_graphrag(enabled=False, build_status="built", is_broad_intent=True)
    payload = decision.as_dict()
    assert payload["mode_note"] is None
    assert payload["use_graphrag"] is False
    assert payload["fallback_mode"] == "hybrid"
    assert "disabled" in payload["warning"]


def test_as_dict_full_shape_on_graphrag_path() -> None:
    """as_dict() carries mode_note and no warning on the all-clear path."""
    decision = decide_graphrag(enabled=True, build_status="built", is_broad_intent=True)
    assert decision.as_dict() == {
        "use_graphrag": True,
        "fallback_mode": "hybrid",
        "warning": None,
        "mode_note": "обзорный ответ на основе community summaries",
    }


def test_custom_fallback_mode_is_carried() -> None:
    """A custom fallback name is propagated to fallback_mode on decline."""
    decision = decide_graphrag(
        enabled=True, build_status=None, is_broad_intent=True, fallback="bm25"
    )
    assert decision.fallback_mode == "bm25"
    assert decision.use_graphrag is False


def test_disabled_takes_priority_over_missing_build() -> None:
    """Feature-off is reported before build/intent causes."""
    decision = decide_graphrag(enabled=False, build_status=None, is_broad_intent=False)
    assert decision.warning == "graphrag disabled"


def test_decision_is_frozen() -> None:
    """GateDecision is an immutable frozen dataclass."""
    decision = GateDecision(True, "hybrid", None, "note")
    try:
        decision.use_graphrag = False  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("GateDecision should be frozen")
