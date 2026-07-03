"""Tests for §10.5 failed-run blast-radius — тесты радиуса поражения (§10.5)."""

from __future__ import annotations

import pytest

from kg_common.metadata.pipeline_failure_impact import (
    DEFAULT_TERMINAL_STEPS,
    FailureImpact,
    downstream_steps,
    impact,
)
from kg_common.metadata.pipeline_lineage_spec import PIPELINE_STEPS, StepSpec

ALL_STEP_NAMES = tuple(step.name for step in PIPELINE_STEPS)


def test_register_source_reaches_every_downstream_step() -> None:
    # The root step blocks all eleven remaining steps.
    blocked = downstream_steps("register_source")
    assert blocked == tuple(sorted(n for n in ALL_STEP_NAMES if n != "register_source"))
    assert "register_source" not in blocked
    assert len(blocked) == len(ALL_STEP_NAMES) - 1


def test_register_source_impacts_all_three_stores() -> None:
    result = impact("register_source")
    assert result.is_terminal_impact is True
    for store in DEFAULT_TERMINAL_STEPS:
        assert store in result.impacted_stores
    assert set(result.impacted_stores) == set(DEFAULT_TERMINAL_STEPS)


def test_neo4j_upsert_is_terminal_leaf() -> None:
    result = impact("neo4j_upsert")
    assert result.blocked_steps == ()
    assert result.impacted_stores == ("neo4j_upsert",)
    assert result.is_terminal_impact is True


def test_early_chunk_step_blocks_extract_normalize_and_all_stores() -> None:
    result = impact("chunk")
    assert "extract" in result.blocked_steps
    assert "normalize_units" in result.blocked_steps
    assert set(result.impacted_stores) == set(DEFAULT_TERMINAL_STEPS)
    assert result.is_terminal_impact is True


@pytest.mark.parametrize("store_step", DEFAULT_TERMINAL_STEPS)
def test_terminal_store_step_has_no_downstream(store_step: str) -> None:
    assert downstream_steps(store_step) == ()


def test_unknown_step_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="bogus_step"):
        downstream_steps("bogus_step")
    with pytest.raises(ValueError, match="bogus_step"):
        impact("bogus_step")


@pytest.mark.parametrize("step_name", ALL_STEP_NAMES)
def test_impacted_stores_sorted_subset_of_terminal(step_name: str) -> None:
    result = impact(step_name)
    stores = result.impacted_stores
    assert list(stores) == sorted(stores)
    assert set(stores) <= set(DEFAULT_TERMINAL_STEPS)
    assert result.is_terminal_impact is bool(stores)


@pytest.mark.parametrize("step_name", ALL_STEP_NAMES)
def test_blocked_never_contains_failed_step(step_name: str) -> None:
    result = impact(step_name)
    assert step_name not in result.blocked_steps
    assert list(result.blocked_steps) == sorted(result.blocked_steps)


def test_non_store_leaf_gap_scan_has_no_terminal_impact() -> None:
    result = impact("gap_scan")
    assert result.blocked_steps == ()
    assert result.impacted_stores == ()
    assert result.is_terminal_impact is False


def test_failureimpact_as_dict_roundtrips() -> None:
    result = impact("chunk")
    payload = result.as_dict()
    assert payload["failed_step"] == "chunk"
    assert isinstance(payload["blocked_steps"], list)
    assert isinstance(payload["impacted_stores"], list)
    assert payload["is_terminal_impact"] is True
    assert set(payload["impacted_stores"]) == set(DEFAULT_TERMINAL_STEPS)


def test_frozen_dataclass_is_immutable() -> None:
    result = impact("gap_scan")
    assert isinstance(result, FailureImpact)
    with pytest.raises((AttributeError, TypeError)):
        result.failed_step = "other"  # type: ignore[misc]


def test_downstream_on_custom_two_step_graph() -> None:
    # Hand-checkable mini-DAG: a -> b via dataset x; b is a leaf.
    steps = (
        StepSpec("a", (), ("x",)),
        StepSpec("b", ("x",), ()),
    )
    assert downstream_steps("a", steps) == ("b",)
    assert downstream_steps("b", steps) == ()
    result = impact("a", steps, terminal=("b",))
    assert result.blocked_steps == ("b",)
    assert result.impacted_stores == ("b",)
    assert result.is_terminal_impact is True
