"""Tests for the §25.10 context-keyed recall fallback chain.

Expected recalls are the hand-checkable heuristic constants: ``catalog_row=0.98``,
``table_row=0.90``, ``prose=0.55`` online / ``0.15`` offline, neutral ``default=0.5``.
"""

from __future__ import annotations

from kg_retrievers.modality_recall import (
    MODALITY_PRIORS,
    ContextRecall,
    recall_for_context,
)


def _ctx(**over: object) -> dict:
    base = {
        "source_type": "pdf",
        "kind": "prose",
        "parser_version": "p1",
        "extractor_version": "e1",
    }
    base.update(over)
    return base


def test_module_priors_have_spec_heuristics() -> None:
    assert MODALITY_PRIORS == {"catalog_row": 0.98, "table_row": 0.90, "prose": 0.55}


def test_exact_priors_hit_wins() -> None:
    # A calibrated telemetry prior keyed on the full composite key beats every
    # heuristic fallback and is stamped source='exact', calibrated=True (§25.10).
    ctx = _ctx(kind="catalog_row")
    key = "pdf|catalog_row|p1|e1"
    result = recall_for_context(ctx, {key: 0.42})

    assert result.source == "exact"
    assert result.recall == 0.42  # the supplied prior, not the 0.98 modality heuristic
    assert result.context_key == key
    assert result.calibrated is True


def test_unknown_key_falls_back_to_catalog_modality() -> None:
    # No priors table → the catalog_row modality heuristic (0.98) applies (§25.10).
    result = recall_for_context(_ctx(kind="catalog_row"))

    assert result.source == "modality"
    assert result.recall == 0.98
    assert result.calibrated is False
    assert result.context_key == "catalog_row"


def test_table_row_modality_heuristic() -> None:
    result = recall_for_context(_ctx(kind="table_row"))

    assert result.source == "modality"
    assert result.recall == 0.90


def test_prose_offline_vs_online_split() -> None:
    # Prose recall hinges on whether an LLM extractor ran: 0.55 online, 0.15 offline.
    online = recall_for_context(_ctx(kind="prose"), offline=False)
    offline = recall_for_context(_ctx(kind="prose"), offline=True)

    assert online.recall == 0.55
    assert online.source == "modality"
    assert offline.recall == 0.15
    assert offline.source == "modality"
    assert offline.calibrated is False


def test_offline_flag_does_not_change_structured_modalities() -> None:
    # Only prose has an offline override; structured rows are LLM-independent.
    assert recall_for_context(_ctx(kind="catalog_row"), offline=True).recall == 0.98
    assert recall_for_context(_ctx(kind="table_row"), offline=True).recall == 0.90


def test_wholly_unknown_kind_falls_back_to_default() -> None:
    # A kind with no modality prior collapses to the neutral default (§25.10).
    result = recall_for_context(_ctx(kind="figure_caption"))

    assert result.source == "default"
    assert result.recall == 0.5
    assert result.calibrated is False


def test_custom_default_is_honoured() -> None:
    result = recall_for_context(_ctx(kind="unknown"), default=0.33)

    assert result.source == "default"
    assert result.recall == 0.33


def test_as_dict_round_trip() -> None:
    result = recall_for_context(_ctx(kind="catalog_row"))
    dumped = result.as_dict()

    assert dumped["context_key"] == "catalog_row"
    assert dumped["source"] == "modality"
    assert dumped["recall"] == 0.98
    assert dumped["calibrated"] is False


def test_context_recall_is_frozen() -> None:
    import dataclasses

    cr = ContextRecall(context_key="k", recall=0.5, source="default")
    try:
        cr.recall = 0.9  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ContextRecall must be frozen")
