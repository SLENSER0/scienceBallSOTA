"""§12.10 — hand-checkable tests for the static Cypher cost/complexity guard."""

from __future__ import annotations

from kg_retrievers.cypher_cost_guard import CostEstimate, estimate_cost


def test_simple_connected_match_not_cartesian_not_blocked() -> None:
    est = estimate_cost("MATCH (a)-[:R]->(b) RETURN a LIMIT 1")
    assert est.has_cartesian is False
    assert est.blocked is False
    assert est.reason is None
    assert est.match_count == 1
    assert est.var_length_hops == 0
    # cost = 100 * 1 * (0 or 1) * 1 = 100
    assert est.estimated_cost == 100


def test_comma_separated_disconnected_patterns_are_cartesian_and_blocked() -> None:
    est = estimate_cost("MATCH (a),(b) RETURN a")
    assert est.has_cartesian is True
    assert est.blocked is True
    assert est.reason is not None
    # penalty applied: 100 * 1 * 1 * 10 = 1000
    assert est.estimated_cost == 1000


def test_variable_length_upper_bound_extracted() -> None:
    est = estimate_cost("MATCH (a)-[*1..5]->(b) RETURN a")
    assert est.var_length_hops == 5
    assert est.has_cartesian is False
    # cost = 100 * 1 * 5 * 1 = 500
    assert est.estimated_cost == 500


def test_cost_exceeding_max_is_blocked_with_reason() -> None:
    # var-length 200 -> cost = 100 * 1 * 200 * 1 = 20000 > 10000
    est = estimate_cost("MATCH (a)-[*1..200]->(b) RETURN a")
    assert est.has_cartesian is False
    assert est.estimated_cost == 20000
    assert est.blocked is True
    assert est.reason is not None
    assert "20000" in est.reason


def test_string_literal_containing_match_is_not_counted() -> None:
    est = estimate_cost("MATCH (a) WHERE a.name = 'MATCH x' RETURN a")
    # only the real MATCH clause is counted, not the word inside the string
    assert est.match_count == 1
    assert est.has_cartesian is False
    assert est.blocked is False


def test_two_matches_sharing_a_variable_not_cartesian() -> None:
    est = estimate_cost("MATCH (a)-[:R]->(b) MATCH (a)-[:S]->(c) RETURN a")
    assert est.match_count == 2
    assert est.has_cartesian is False
    assert est.blocked is False


def test_later_match_sharing_no_variable_is_cartesian() -> None:
    est = estimate_cost("MATCH (a)-[:R]->(b) MATCH (c)-[:S]->(d) RETURN a")
    assert est.has_cartesian is True
    assert est.blocked is True


def test_as_dict_round_trips_all_six_fields() -> None:
    est = estimate_cost("MATCH (a),(b) RETURN a")
    d = est.as_dict()
    assert set(d) == {
        "match_count",
        "var_length_hops",
        "has_cartesian",
        "estimated_cost",
        "blocked",
        "reason",
    }
    assert d["match_count"] == est.match_count
    assert d["var_length_hops"] == est.var_length_hops
    assert d["has_cartesian"] == est.has_cartesian
    assert d["estimated_cost"] == est.estimated_cost
    assert d["blocked"] == est.blocked
    assert d["reason"] == est.reason
    # round-trip: rebuilding from the dict yields an equal estimate
    assert CostEstimate(**d) == est


def test_custom_thresholds_respected() -> None:
    est = estimate_cost(
        "MATCH (a)-[*1..3]->(b) RETURN a",
        max_cost=200,
        base_per_match=100,
    )
    # cost = 100 * 1 * 3 * 1 = 300 > 200
    assert est.estimated_cost == 300
    assert est.blocked is True
