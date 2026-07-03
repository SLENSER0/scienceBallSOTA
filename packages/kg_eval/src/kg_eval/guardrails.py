"""[DE] Recall-prior guardrail (spec §33.9, port of science_ball A3).

Cross-checks the per-modality recall **prior** the absence layer would assume
(:func:`kg_eval.recall_model.base_recall`) against recall actually **measured** by
Track-A (:func:`kg_eval.matching.evaluate_extraction_semantic`). Read-only: it
reports divergence, never rewrites a prior. The concrete bug it guards: the
``chunk`` prior claims ~0.55 recall when the LLM prose extractor is "enabled", but
the pipeline commits ~0 numeric prose observations, so measured prose recall ≈ 0 —
a >0.30 divergence that collapses the absence verdict into the abstain band.
"""

from __future__ import annotations

from typing import Any

from kg_eval.recall_model import base_recall


def check_recall_priors(
    track_a: dict[str, Any],
    *,
    prose_extraction_enabled: bool,
    tolerance: float = 0.30,
    prose_observations_committed: bool | None = None,
) -> dict[str, Any]:
    """Flag modalities whose prior diverges from measured semantic recall by > tolerance."""
    checks: list[dict[str, Any]] = []
    findings: list[str] = []
    for mod, agg in sorted((track_a.get("by_modality") or {}).items()):
        measured = agg.get("semantic_recall")
        if measured is None:
            continue
        prior = round(
            base_recall(
                mod,
                prose_extraction_enabled,
                prose_observations_committed=prose_observations_committed,
            ),
            3,
        )
        divergence = round(abs(prior - measured), 4)
        over = divergence > tolerance
        checks.append(
            {
                "modality": mod,
                "prior": prior,
                "measured_recall": measured,
                "divergence": divergence,
                "over_tolerance": over,
                "expected": agg.get("expected"),
            }
        )
        if over:
            findings.append(
                f"recall prior for `{mod}` = {prior} but MEASURED semantic recall = "
                f"{measured} (divergence {divergence} > tolerance {tolerance}) — the prior "
                f"OVERSTATES what the pipeline actually commits, so the absence verdict built "
                f"on it will mis-decide (prose_extraction_enabled={prose_extraction_enabled})."
            )
    return {
        "tolerance": tolerance,
        "prose_extraction_enabled": prose_extraction_enabled,
        "checks": checks,
        "findings": findings,
        "ok": not findings,
    }
