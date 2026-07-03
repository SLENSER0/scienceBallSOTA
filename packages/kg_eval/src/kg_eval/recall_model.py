"""[DE] Per-modality base-recall model for the benchmark guardrail (§33, port of A3/N1).

SOTA's production recall layer (:mod:`kg_retrievers.recall_priors`) derives an
*empirical* Beta-smoothed recall keyed on ``target_type`` and carries **no**
modality (chunk-vs-table) dimension. The Track-A guardrail (D9), by contrast, needs
a per-**modality** prior to compare against measured semantic recall, and the N1
honest-prior toggle (D14) needs a prose committed-floor. This module supplies that
static modality-recall model — a benchmark-side lens, never written into the
production graph.
"""

from __future__ import annotations

# Per-modality prior recall the absence layer would assume.
MODALITY_BASE_RECALL: dict[str, float] = {
    "catalog_row": 0.98,  # structured LIMS/ELN export — near complete
    "table_row": 0.90,  # document tables parsed deterministically
    "caption": 0.50,  # figure/table captions — partial
    "chunk": 0.55,  # prose WITH the LLM prose extractor enabled
}
PROSE_KIND = "chunk"
PROSE_RECALL_NO_EXTRACTION = 0.15  # prose recall when the LLM extractor is offline
DEFAULT_RECALL = 0.50


def base_recall(
    kind: str | None,
    prose_extraction_enabled: bool,
    *,
    prose_observations_committed: bool | None = None,
) -> float:
    """Prior recall for a modality (N1 committed-floor logic).

    ``prose_observations_committed`` (prose ``chunk`` only): ``None`` = legacy
    (commit == read → 0.55 if the LLM is on, else 0.15); ``False`` = the honest
    committed floor 0.15 regardless of readability (prose candidates are
    review-gated, not auto-committed); ``True`` = 0.55. Non-prose kinds ignore it.
    """
    if kind == PROSE_KIND:
        if prose_observations_committed is None:
            prose_observations_committed = prose_extraction_enabled  # legacy: commit == read
        return (
            MODALITY_BASE_RECALL["chunk"]
            if prose_observations_committed
            else PROSE_RECALL_NO_EXTRACTION
        )
    return MODALITY_BASE_RECALL.get(kind or "", DEFAULT_RECALL)
