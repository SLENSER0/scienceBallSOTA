"""§13.10 tests for :mod:`agent_service.query_plan` — QueryPlan + expand-on-retry.

Real, hand-checkable assertions: allow-list validation, JSON serialisation and the
expand-on-retry merge semantics (order-preserving, de-duplicated).
"""

from __future__ import annotations

import pytest
from agent_service.query_plan import (
    OUTPUT_ALLOWLIST,
    STRATEGY_ALLOWLIST,
    QueryPlan,
    expand_plan,
)


def _valid_plan(strategies: tuple[str, ...] = ("cypher_template",)) -> QueryPlan:
    """Build a minimal valid plan for reuse across tests."""
    return QueryPlan(
        intent="material_regime_property_query",
        entities={"material": "Ti-6Al-4V"},
        numeric_constraints={"temperature_C": (150, 250)},
        retrieval_strategy=strategies,
        expected_outputs=("summary", "experiments_table"),
    )


def test_allowlists_are_the_spec_sets() -> None:
    """The two allow-lists match the §13.10 spec exactly."""
    assert {
        "cypher_template",
        "hybrid_chunks",
        "evidence_lookup",
        "gap_scan",
        "graphrag_community",
        "graph_algo",
    } == STRATEGY_ALLOWLIST
    assert {"summary", "experiments_table", "graph", "gaps"} == OUTPUT_ALLOWLIST


def test_invalid_strategy_raises() -> None:
    """(1) A strategy outside the allow-list raises ``ValueError``."""
    with pytest.raises(ValueError, match="bogus"):
        QueryPlan(
            intent="x",
            retrieval_strategy=("bogus",),
            expected_outputs=("summary",),
        )


def test_valid_plan_builds_and_serialises_as_list() -> None:
    """(2) A valid plan builds; ``as_dict()['retrieval_strategy']`` is a list."""
    plan = _valid_plan()
    payload = plan.as_dict()
    assert isinstance(payload["retrieval_strategy"], list)
    assert payload["retrieval_strategy"] == ["cypher_template"]
    assert isinstance(payload["expected_outputs"], list)
    assert payload["intent"] == "material_regime_property_query"
    # entities / numeric_constraints round-trip as plain dicts.
    assert payload["entities"] == {"material": "Ti-6Al-4V"}
    assert payload["numeric_constraints"] == {"temperature_C": (150, 250)}


def test_expand_plan_appends_suggested_strategy() -> None:
    """(3) Expanding ('cypher_template',) with 'gap_scan' yields both, in order."""
    plan = _valid_plan(("cypher_template",))
    expanded = expand_plan(plan, {"suggest": ["gap_scan"]})
    assert expanded.retrieval_strategy == ("cypher_template", "gap_scan")
    # A new object is returned; the original is untouched (frozen, immutable).
    assert plan.retrieval_strategy == ("cypher_template",)
    assert expanded is not plan


def test_expand_plan_dedupes_already_present_strategy() -> None:
    """(4) Suggesting an already-present strategy produces no duplicate."""
    plan = _valid_plan(("cypher_template", "hybrid_chunks"))
    expanded = expand_plan(plan, {"suggest": ["cypher_template"]})
    assert expanded.retrieval_strategy == ("cypher_template", "hybrid_chunks")


def test_expand_plan_preserves_original_order() -> None:
    """(5) Original strategies keep their order; new ones append after."""
    plan = _valid_plan(("hybrid_chunks", "cypher_template"))
    expanded = expand_plan(plan, {"suggest": ["gap_scan", "evidence_lookup"]})
    assert expanded.retrieval_strategy == (
        "hybrid_chunks",
        "cypher_template",
        "gap_scan",
        "evidence_lookup",
    )


def test_invalid_expected_output_raises() -> None:
    """(6) An expected output outside the allow-list raises ``ValueError``."""
    with pytest.raises(ValueError, match="not_an_output"):
        QueryPlan(
            intent="x",
            retrieval_strategy=("cypher_template",),
            expected_outputs=("not_an_output",),
        )


def test_expand_plan_empty_suggest_is_noop() -> None:
    """(7) An empty / missing ``suggest`` leaves the plan strategies unchanged."""
    plan = _valid_plan(("cypher_template", "hybrid_chunks"))
    assert expand_plan(plan, {"suggest": []}).retrieval_strategy == (
        "cypher_template",
        "hybrid_chunks",
    )
    assert expand_plan(plan, {}).retrieval_strategy == (
        "cypher_template",
        "hybrid_chunks",
    )


def test_expand_plan_carries_other_fields_and_stays_valid() -> None:
    """Expansion preserves intent/entities/outputs and re-validates the new plan."""
    plan = _valid_plan(("cypher_template",))
    expanded = expand_plan(plan, {"suggest": ["gap_scan"]})
    assert expanded.intent == plan.intent
    assert expanded.entities == plan.entities
    assert expanded.numeric_constraints == plan.numeric_constraints
    assert expanded.expected_outputs == plan.expected_outputs
    # A suggested strategy outside the allow-list is still rejected on expand.
    with pytest.raises(ValueError, match="nope"):
        expand_plan(plan, {"suggest": ["nope"]})


def test_expand_plan_accepts_scalar_suggest() -> None:
    """A lone strategy string in ``suggest`` is treated as a one-element sequence."""
    plan = _valid_plan(("cypher_template",))
    expanded = expand_plan(plan, {"suggest": "gap_scan"})
    assert expanded.retrieval_strategy == ("cypher_template", "gap_scan")
