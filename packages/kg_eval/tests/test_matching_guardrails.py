"""[DE] Track-A semantic matching + recall-prior guardrail (§33, D8/D9).

On the offline synthetic corpus the deterministic paths (table/catalog) extract
their facts (semantic_recall=1.0) while prose (chunk) is the measured blind spot
(0.0). The guardrail is quiet offline (prose prior 0.15 ≈ measured 0.0) but fires
when the prose extractor is claimed "on" (prior 0.55 vs measured 0.0).
"""

from __future__ import annotations

from kg_eval.datasets.loader import load_synthetic
from kg_eval.guardrails import check_recall_priors
from kg_eval.matching import evaluate_extraction_semantic


def test_semantic_recall_by_modality() -> None:
    with load_synthetic() as ctx:
        tra = evaluate_extraction_semantic(ctx.store, ctx.manifest.extraction_gold)
        by = tra["by_modality"]
        assert by["table_row"]["semantic_recall"] == 1.0
        assert by["catalog_row"]["semantic_recall"] == 1.0
        assert by["chunk"]["semantic_recall"] == 0.0  # offline prose blind spot
        assert tra["deterministic_semantic_recall"] == 1.0
        # value precision among evidence-found facts is perfect on table/catalog
        assert by["table_row"]["value_precision"] == 1.0


def test_guardrail_quiet_offline_fires_when_prose_claimed_on() -> None:
    with load_synthetic() as ctx:
        tra = evaluate_extraction_semantic(ctx.store, ctx.manifest.extraction_gold)
        # offline: chunk prior floored to 0.15, close to measured 0.0 → no flag.
        offline = check_recall_priors(tra, prose_extraction_enabled=False)
        assert offline["ok"] is True and offline["findings"] == []
        # prose "on": chunk prior 0.55 vs measured 0.0 → divergence 0.55 > 0.30 → ⚠️.
        live = check_recall_priors(tra, prose_extraction_enabled=True)
        assert live["ok"] is False
        assert any(c["modality"] == "chunk" and c["over_tolerance"] for c in live["checks"])
        assert live["findings"]


def test_honest_committed_floor_silences_the_flag() -> None:
    # N1 (D14): even with the LLM "on", passing prose_observations_committed=False
    # floors the prose prior to 0.15, so the guardrail no longer flags it.
    with load_synthetic() as ctx:
        tra = evaluate_extraction_semantic(ctx.store, ctx.manifest.extraction_gold)
        honest = check_recall_priors(
            tra, prose_extraction_enabled=True, prose_observations_committed=False
        )
        assert honest["ok"] is True
