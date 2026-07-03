"""Static heuristic modality recall-prior table (§25.10).

Where :mod:`kg_retrievers.recall_priors` *derives* extractor recall (полнота
извлечения) empirically from coverage telemetry, this module holds the **static**
fallback used before any telemetry exists: a per-modality (по модальности) prior
keyed on how a fact was surfaced. A structured ``catalog_row`` is almost always
extracted (recall ≈ 0.98); a free-text ``prose`` span depends heavily on whether an
LLM extractor ran (0.55) or only an offline/regex pass did (0.15).

Resolution is exact → modality → default: an exact ``context_key`` hit wins; else a
key that merely *contains* a known modality substring inherits that modality's prior;
else the neutral :data:`DEFAULT_PRIOR`. Every result is a frozen
:class:`ModalityPrior` marked ``calibrated=False`` — these are heuristics, never
telemetry-calibrated numbers, and the absence layer (§25.11) must treat them as such.
"""

from __future__ import annotations

from dataclasses import dataclass

# Per-modality heuristic recall priors (§25.10). Structured rows are near-certain to
# be extracted; prose recall splits on whether an LLM extractor was available.
CATALOG_ROW: float = 0.98
TABLE_ROW: float = 0.90
PROSE_LLM: float = 0.55
PROSE_OFFLINE: float = 0.15

# Neutral fallback when neither an exact key nor a modality substring matches.
DEFAULT_PRIOR: float = 0.70

# Method tag stamped on every result so downstream code can distinguish these static
# heuristics from telemetry-calibrated priors (§25.10 / §25.11).
_METHOD: str = "heuristic_modality_prior"

# Known modality substrings, longest-first so ``document_table_row`` matches
# ``table_row`` and never the shorter fragments of another key.
_MODALITY_KEYS: tuple[str, ...] = ("catalog_row", "table_row", "prose")


@dataclass(frozen=True)
class ModalityPrior:
    """One resolved modality recall prior (§25.10).

    ``context_key`` — the modality/context this prior applies to; ``recall`` — its
    heuristic recall in ``[0, 1]``; ``source`` — how it was resolved (``'exact'`` /
    ``'modality'`` / ``'default'``); ``calibrated`` — always ``False`` for heuristics.
    """

    context_key: str
    recall: float
    source: str
    calibrated: bool = False
    method: str = _METHOD

    def as_dict(self) -> dict:
        return {
            "context_key": self.context_key,
            "recall": self.recall,
            "source": self.source,
            "calibrated": self.calibrated,
            "method": self.method,
        }


def default_modality_priors(*, llm_enabled: bool) -> dict[str, float]:
    """Static per-modality prior table (§25.10).

    ``prose`` resolves to :data:`PROSE_LLM` when an LLM extractor is available and to
    :data:`PROSE_OFFLINE` otherwise; structured modalities are LLM-independent.
    """
    return {
        "catalog_row": CATALOG_ROW,
        "table_row": TABLE_ROW,
        "prose": PROSE_LLM if llm_enabled else PROSE_OFFLINE,
    }


def recall_for_context(
    context_key: str,
    priors: dict[str, float] | None = None,
    *,
    llm_enabled: bool = True,
    default: float = DEFAULT_PRIOR,
) -> ModalityPrior:
    """Resolve a modality recall prior for ``context_key`` (§25.10).

    Exact key hit → ``source='exact'``; else the first known modality substring the
    key contains → ``source='modality'``; else ``default`` → ``source='default'``.
    """
    table = priors if priors is not None else default_modality_priors(llm_enabled=llm_enabled)

    if context_key in table:
        return ModalityPrior(context_key=context_key, recall=table[context_key], source="exact")

    for modality in _MODALITY_KEYS:
        if modality in context_key and modality in table:
            return ModalityPrior(context_key=modality, recall=table[modality], source="modality")

    return ModalityPrior(context_key=context_key, recall=default, source="default")
