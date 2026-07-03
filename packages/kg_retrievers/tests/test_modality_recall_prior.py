"""Tests for the static heuristic modality recall-prior table (§25.10)."""

from __future__ import annotations

from kg_retrievers.modality_recall_prior import (
    CATALOG_ROW,
    DEFAULT_PRIOR,
    PROSE_LLM,
    PROSE_OFFLINE,
    TABLE_ROW,
    ModalityPrior,
    default_modality_priors,
    recall_for_context,
)


def test_constants_have_expected_values() -> None:
    assert CATALOG_ROW == 0.98
    assert TABLE_ROW == 0.90
    assert PROSE_LLM == 0.55
    assert PROSE_OFFLINE == 0.15
    assert DEFAULT_PRIOR == 0.70


def test_catalog_row_exact_hit() -> None:
    # Assertion (1): exact key -> recall 0.98, source 'exact'.
    prior = recall_for_context("catalog_row")
    assert prior.recall == 0.98
    assert prior.source == "exact"


def test_prose_offline_when_llm_disabled() -> None:
    # Assertion (2): prose with llm_enabled False -> 0.15.
    prior = recall_for_context("prose", llm_enabled=False)
    assert prior.recall == 0.15
    assert prior.source == "exact"


def test_prose_llm_when_llm_enabled() -> None:
    # Assertion (3): prose with llm_enabled True -> 0.55.
    prior = recall_for_context("prose", llm_enabled=True)
    assert prior.recall == 0.55
    assert prior.source == "exact"


def test_unknown_key_falls_back_to_default() -> None:
    # Assertion (4): unknown key -> 0.70, source 'default'.
    prior = recall_for_context("something_totally_unknown")
    assert prior.recall == 0.70
    assert prior.source == "default"


def test_every_prior_is_heuristic_and_uncalibrated() -> None:
    # Assertion (5): calibrated False and method tag on every path.
    keys = ["catalog_row", "document_table_row", "prose", "no_such_key"]
    for key in keys:
        prior = recall_for_context(key)
        assert prior.calibrated is False
        assert prior.method == "heuristic_modality_prior"


def test_document_table_row_resolves_via_modality_fallback() -> None:
    # Assertion (6): substring match -> table_row 0.90, source 'modality'.
    prior = recall_for_context("document_table_row")
    assert prior.recall == 0.90
    assert prior.source == "modality"
    assert prior.context_key == "table_row"


def test_default_modality_priors_offline_prose() -> None:
    # Assertion (7): default_modality_priors(llm_enabled=False)['prose'] == 0.15.
    assert default_modality_priors(llm_enabled=False)["prose"] == 0.15
    assert default_modality_priors(llm_enabled=True)["prose"] == 0.55
    assert default_modality_priors(llm_enabled=False)["catalog_row"] == 0.98
    assert default_modality_priors(llm_enabled=False)["table_row"] == 0.90


def test_as_dict_includes_source_and_calibrated() -> None:
    # Assertion (8): as_dict() carries source and calibrated keys.
    payload = recall_for_context("catalog_row").as_dict()
    assert "source" in payload
    assert "calibrated" in payload
    assert payload["source"] == "exact"
    assert payload["calibrated"] is False
    assert payload["recall"] == 0.98
    assert payload["method"] == "heuristic_modality_prior"


def test_explicit_priors_table_overrides_default() -> None:
    # A caller-supplied table is used verbatim for exact + modality resolution.
    custom = {"catalog_row": 0.5, "table_row": 0.4, "prose": 0.3}
    assert recall_for_context("catalog_row", custom).recall == 0.5
    assert recall_for_context("scanned_table_row", custom).recall == 0.4
    assert recall_for_context("mystery", custom).source == "default"


def test_frozen_dataclass_is_immutable() -> None:
    prior = recall_for_context("catalog_row")
    assert isinstance(prior, ModalityPrior)
    try:
        prior.recall = 0.1  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("ModalityPrior must be frozen")
