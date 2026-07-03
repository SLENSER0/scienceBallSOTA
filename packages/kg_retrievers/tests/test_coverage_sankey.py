"""Tests for the coverage sankey builder (§17.14 / §5.2.7).

Hand-checkable assertions over the pure ``build_coverage_sankey`` builder: node depths,
column-prefixed names, count aggregation and JSON-serialisability (RU: проверки покрытия).
"""

from __future__ import annotations

import json

from kg_retrievers.coverage_sankey import SankeyPayload, build_coverage_sankey


def test_empty_input_yields_empty_payload() -> None:
    """Empty input -> nodes==() and links==() (§17.14)."""
    payload = build_coverage_sankey([])
    assert isinstance(payload, SankeyPayload)
    assert payload.nodes == ()
    assert payload.links == ()
    assert payload.as_dict() == {"nodes": [], "links": []}


def test_single_triple_three_nodes_two_links() -> None:
    """One triple -> 3 nodes depths 0/1/2 and 2 links each value 3 (§17.14)."""
    payload = build_coverage_sankey(
        [{"material": "Al-2024", "regime": "aging", "property": "hardness", "count": 3}]
    )
    assert len(payload.nodes) == 3
    depths = {node["name"]: node["depth"] for node in payload.nodes}
    assert depths == {"M:Al-2024": 0, "R:aging": 1, "P:hardness": 2}

    assert len(payload.links) == 2
    for link in payload.links:
        assert link["value"] == 3
    link_pairs = {(link["source"], link["target"]) for link in payload.links}
    assert link_pairs == {("M:Al-2024", "R:aging"), ("R:aging", "P:hardness")}


def test_shared_material_regime_link_aggregates_and_node_appears_once() -> None:
    """Two triples sharing (Al-2024, aging) -> M->R value==6, material node once (§17.14)."""
    payload = build_coverage_sankey(
        [
            {"material": "Al-2024", "regime": "aging", "property": "hardness", "count": 2},
            {"material": "Al-2024", "regime": "aging", "property": "strength", "count": 4},
        ]
    )
    materials = [n for n in payload.nodes if n["name"] == "M:Al-2024"]
    assert len(materials) == 1

    mr_links = [
        link
        for link in payload.links
        if link["source"] == "M:Al-2024" and link["target"] == "R:aging"
    ]
    assert len(mr_links) == 1
    assert mr_links[0]["value"] == 6


def test_property_via_two_regimes_yields_two_distinct_links() -> None:
    """A property reached via two regimes -> two distinct R->P links (§17.14)."""
    payload = build_coverage_sankey(
        [
            {"material": "Al-2024", "regime": "aging", "property": "hardness", "count": 1},
            {"material": "Al-2024", "regime": "quench", "property": "hardness", "count": 5},
        ]
    )
    rp_links = [link for link in payload.links if link["target"] == "P:hardness"]
    assert len(rp_links) == 2
    assert {link["source"] for link in rp_links} == {"R:aging", "R:quench"}
    assert {link["value"] for link in rp_links} == {1, 5}


def test_property_node_depth_is_two() -> None:
    """Node depth for a Property node == 2 (§5.2.7)."""
    payload = build_coverage_sankey(
        [{"material": "Cu", "regime": "anneal", "property": "ductility", "count": 7}]
    )
    prop_nodes = [n for n in payload.nodes if n["name"].startswith("P:")]
    assert prop_nodes
    for node in prop_nodes:
        assert node["depth"] == 2


def test_link_endpoints_reference_present_nodes() -> None:
    """Every link source/target references a node name present in nodes (§17.14)."""
    payload = build_coverage_sankey(
        [
            {"material": "Al-2024", "regime": "aging", "property": "hardness", "count": 3},
            {"material": "Ti-64", "regime": "hip", "property": "fatigue", "count": 2},
        ]
    )
    names = {node["name"] for node in payload.nodes}
    for link in payload.links:
        assert link["source"] in names
        assert link["target"] in names


def test_as_dict_is_json_serialisable_with_int_values() -> None:
    """as_dict() is JSON-serialisable and link values are ints (§5.2.7)."""
    payload = build_coverage_sankey(
        [{"material": "Al-2024", "regime": "aging", "property": "hardness", "count": 3}]
    )
    encoded = json.dumps(payload.as_dict())
    restored = json.loads(encoded)
    assert set(restored) == {"nodes", "links"}
    for link in payload.as_dict()["links"]:
        assert isinstance(link["value"], int)


def test_string_count_is_coerced_to_int() -> None:
    """A string count is coerced to an int weight (§17.14 robustness)."""
    payload = build_coverage_sankey(
        [{"material": "Al", "regime": "aging", "property": "hardness", "count": "4"}]
    )
    assert all(isinstance(link["value"], int) for link in payload.links)
    assert all(link["value"] == 4 for link in payload.links)
