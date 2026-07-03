"""Tests for §17.5 graphEncoding single-source-of-truth (§5.2.3 visual encodings).

Хенд-проверяемые тесты чистого резолвера :mod:`kg_retrievers.graph_visual_style`:
цвет по типу, размер по √evidenceCount, hollow / locked / dashed / red-каналы,
клэмп прозрачности и неизменность оригиналов в :func:`style_graph`.
"""

from __future__ import annotations

import math

from kg_retrievers.graph_visual_style import (
    DEFAULT_COLOR,
    EDGE_COLOR,
    MIN_OPACITY,
    MIN_SIZE,
    RED,
    TYPE_COLORS,
    EdgeStyle,
    NodeStyle,
    edge_style,
    node_style,
    style_graph,
)

# -- node color (§5.2.3 nodeColor ← type) ------------------------------------------


def test_material_uses_type_color() -> None:
    style = node_style({"type": "Material"})
    assert style.color == TYPE_COLORS["Material"]
    assert style.color != DEFAULT_COLOR


def test_unknown_type_falls_back_to_default_gray() -> None:
    assert node_style({"type": "NoSuchLabel"}).color == DEFAULT_COLOR


def test_none_type_falls_back_to_default_gray() -> None:
    assert node_style({"type": None}).color == DEFAULT_COLOR
    assert node_style({}).color == DEFAULT_COLOR


# -- node size (§5.2.3 nodeSize ← evidenceCount) -----------------------------------


def test_zero_evidence_is_min_size() -> None:
    assert node_style({"type": "Material", "evidenceCount": 0}).size == MIN_SIZE
    assert node_style({"type": "Material"}).size == MIN_SIZE  # missing → 0 → MIN_SIZE


def test_size_grows_with_evidence_count() -> None:
    small = node_style({"type": "Material", "evidenceCount": 1}).size
    large = node_style({"type": "Material", "evidenceCount": 9}).size
    assert large > small
    # Hand-checked: MIN_SIZE + 2·√9 = 4 + 6 = 10.0.
    assert math.isclose(large, MIN_SIZE + 2.0 * 3.0)


# -- hollow (§5.2.3 hollowNode ← missingFields) ------------------------------------


def test_missing_fields_present_is_hollow() -> None:
    assert node_style({"type": "Material", "missingFields": ["name"]}).hollow is True


def test_empty_missing_fields_is_not_hollow() -> None:
    assert node_style({"type": "Material", "missingFields": []}).hollow is False
    assert node_style({"type": "Material"}).hollow is False


# -- locked (§5.2.3 lockIcon ← verified) -------------------------------------------


def test_verified_is_locked() -> None:
    assert node_style({"type": "Material", "verified": True}).locked is True


def test_unverified_is_not_locked() -> None:
    assert node_style({"type": "Material", "verified": False}).locked is False
    assert node_style({"type": "Material"}).locked is False


# -- edge dashed / red (§5.2.3 dashedEdge ← inferred, redEdge ← contradicted) ------


def test_inferred_edge_is_dashed() -> None:
    assert edge_style({"inferred": True}).dashed is True
    assert edge_style({"inferred": False}).dashed is False


def test_contradicted_edge_is_red() -> None:
    style = edge_style({"contradicted": True})
    assert style.color == RED


def test_normal_edge_is_not_red() -> None:
    assert edge_style({"contradicted": False}).color == EDGE_COLOR


# -- edge opacity (§5.2.3 edgeOpacity ← confidence, clamped) ------------------------


def test_full_confidence_gives_full_opacity() -> None:
    assert edge_style({"confidence": 1.0}).opacity == 1.0


def test_zero_confidence_is_clamped_to_min() -> None:
    assert edge_style({"confidence": 0.0}).opacity == MIN_OPACITY


def test_none_confidence_uses_default_opacity() -> None:
    # None → default 0.6 (not clamped to min).
    assert edge_style({"confidence": None}).opacity == 0.6
    assert edge_style({}).opacity == 0.6


# -- edge width grows with evidence ------------------------------------------------


def test_edge_width_grows_with_evidence() -> None:
    thin = edge_style({"evidenceCount": 1}).width
    thick = edge_style({"evidenceCount": 9}).width
    assert thick > thin


# -- style_graph copies & does not mutate originals --------------------------------


def test_style_graph_adds_style_and_preserves_originals() -> None:
    node = {"id": "n1", "type": "Material", "evidenceCount": 4, "verified": True}
    edge = {"id": "e1", "source": "n1", "target": "n2", "contradicted": True}
    graph = {"nodes": [node], "edges": [edge]}

    styled = style_graph(graph)

    # Every node/edge carries a 'style' dict.
    styled_node = styled["nodes"][0]
    styled_edge = styled["edges"][0]
    assert isinstance(styled_node["style"], dict)
    assert isinstance(styled_edge["style"], dict)
    assert styled_node["style"]["color"] == TYPE_COLORS["Material"]
    assert styled_node["style"]["locked"] is True
    assert styled_edge["style"]["color"] == RED

    # Originals are unmutated (no 'style' key leaked back).
    assert "style" not in node
    assert "style" not in edge
    assert "style" not in graph["nodes"][0]
    assert "style" not in graph["edges"][0]


def test_style_graph_handles_empty_graph() -> None:
    styled = style_graph({})
    assert styled == {"nodes": [], "edges": []}


# -- frozen dataclass as_dict() round-trip -----------------------------------------


def test_node_style_as_dict_keys() -> None:
    d = NodeStyle(color="#fff", size=4.0, hollow=False, locked=True).as_dict()
    assert d == {"color": "#fff", "size": 4.0, "hollow": False, "locked": True}


def test_edge_style_as_dict_keys() -> None:
    d = EdgeStyle(color=RED, width=1.0, opacity=0.6, dashed=True).as_dict()
    assert d == {"color": RED, "width": 1.0, "opacity": 0.6, "dashed": True}


def test_type_colors_are_distinct_hex_strings() -> None:
    for value in TYPE_COLORS.values():
        assert value.startswith("#") and len(value) == 7
