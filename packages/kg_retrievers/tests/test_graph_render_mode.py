"""Tests for the §17.8/§17.9 graph render-mode + layout auto-switch selector."""

from __future__ import annotations

from kg_retrievers.graph_render_mode import (
    DEFAULT_MODE,
    MODE_LAYOUTS,
    RenderModeDecision,
    available_layouts,
    choose_render_mode,
)


def test_small_graph_defaults_to_reagraph() -> None:
    decision = choose_render_mode(100, 50)
    assert decision.mode == "reagraph"
    assert decision.mode == DEFAULT_MODE
    assert "default" in decision.reason
    assert decision.node_count == 100
    assert decision.edge_count == 50
    assert decision.layouts == MODE_LAYOUTS["reagraph"]


def test_threshold_auto_switches_to_sigma() -> None:
    decision = choose_render_mode(2000, 0)
    assert decision.mode == "sigma"
    assert "threshold" in decision.reason
    assert decision.layouts == MODE_LAYOUTS["sigma"]


def test_just_below_threshold_stays_reagraph() -> None:
    assert choose_render_mode(1999, 0).mode == "reagraph"


def test_valid_requested_always_wins_over_threshold() -> None:
    decision = choose_render_mode(2500, 0, requested="cytoscape")
    assert decision.mode == "cytoscape"
    assert "requested" in decision.reason
    assert decision.layouts == MODE_LAYOUTS["cytoscape"]


def test_valid_requested_wins_on_small_graph() -> None:
    decision = choose_render_mode(10, 0, requested="force3d")
    assert decision.mode == "force3d"
    assert "requested" in decision.reason
    assert decision.layouts == MODE_LAYOUTS["force3d"]


def test_requested_reagraph_on_large_graph_overrides_auto() -> None:
    # An explicit valid request beats the sigma auto-switch even above threshold.
    decision = choose_render_mode(9000, 100, requested="reagraph")
    assert decision.mode == "reagraph"
    assert "requested" in decision.reason


def test_invalid_requested_ignored_auto_rules_apply_large() -> None:
    decision = choose_render_mode(3000, 0, requested="bogus")
    assert decision.mode == "sigma"
    assert "threshold" in decision.reason


def test_invalid_requested_ignored_auto_rules_apply_small() -> None:
    decision = choose_render_mode(5, 0, requested="bogus")
    assert decision.mode == "reagraph"
    assert "default" in decision.reason


def test_custom_sigma_threshold_respected() -> None:
    assert choose_render_mode(600, 0, sigma_threshold=500).mode == "sigma"
    assert choose_render_mode(400, 0, sigma_threshold=500).mode == "reagraph"


def test_available_layouts_reagraph_exact() -> None:
    assert available_layouts("reagraph") == (
        "forceDirected2d",
        "radial",
        "hierarchical",
        "circular",
    )


def test_available_layouts_sigma_contains_forceatlas2() -> None:
    assert "forceatlas2" in available_layouts("sigma")


def test_available_layouts_unknown_mode_empty() -> None:
    assert available_layouts("nope") == ()


def test_all_modes_present() -> None:
    assert set(MODE_LAYOUTS) == {"reagraph", "sigma", "cytoscape", "force3d"}
    for layouts in MODE_LAYOUTS.values():
        assert isinstance(layouts, tuple)
        assert len(layouts) >= 1


def test_as_dict_keys_and_values() -> None:
    decision = choose_render_mode(2500, 12, requested="sigma")
    payload = decision.as_dict()
    assert set(payload) == {"mode", "reason", "nodeCount", "edgeCount", "layouts"}
    assert payload["mode"] == "sigma"
    assert payload["nodeCount"] == 2500
    assert payload["edgeCount"] == 12
    assert payload["layouts"] == list(MODE_LAYOUTS["sigma"])


def test_decision_is_frozen() -> None:
    decision = choose_render_mode(1, 1)
    assert isinstance(decision, RenderModeDecision)
    try:
        decision.mode = "sigma"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("RenderModeDecision must be frozen")
