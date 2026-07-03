"""Gold-set recall calibration with Jeffreys smoothing (§25.17).

Unlike :mod:`kg_retrievers.recall_priors` — which *derives* extractor recall from
runtime coverage telemetry — this module *calibrates* recall against a curated
**gold set** (эталонная выборка): a list of facts a human confirmed the corpus
contains, grouped by modality. For each modality we count how many gold facts the
extractor actually recovered (``k``) out of the group size (``n``) and report a
Jeffreys-smoothed recall estimate::

    recall = (k + 0.5) / (n + 1)

The Jeffreys prior (Beta(1/2, 1/2)) keeps the estimate strictly inside ``(0, 1)``:
a modality where every gold fact was matched (``k == n``) reads slightly below a
naive ``1.0``, and an empty group (``n == 0``) collapses to the neutral ``0.5``
rather than an undefined ``0/0``. The un-smoothed hit-rate is preserved alongside
as ``recall_raw`` so callers can see both. Modalities with fewer than ``min_n``
gold facts are flagged ``low_confidence`` (мало наблюдений).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Jeffreys prior Beta(1/2, 1/2): pseudo-counts added to successes and total.
_JEFFREYS_ALPHA: float = 0.5
_JEFFREYS_PRIOR_MASS: float = 1.0
# Default minimum gold-group size below which an estimate is thinly-sampled.
DEFAULT_MIN_N: int = 5


@dataclass(frozen=True, slots=True)
class CalibratedPrior:
    """A gold-calibrated recall estimate for one modality (§25.17).

    Одна оценка полноты (recall), откалиброванная по эталонной выборке.

    ``recall_raw`` is the un-smoothed hit-rate ``k / n``; ``recall`` is the
    Jeffreys-smoothed ``(k + 0.5) / (n + 1)``. ``low_confidence`` marks
    thinly-sampled modalities (``n < min_n``).
    """

    context_key: str
    modality: str
    k: int
    n: int
    recall_raw: float
    recall: float
    low_confidence: bool
    calibrated: bool = True
    method: str = "gold_calibrated"

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict, exposing both raw and smoothed recall."""
        return {
            "context_key": self.context_key,
            "modality": self.modality,
            "k": self.k,
            "n": self.n,
            "recall_raw": self.recall_raw,
            "recall": self.recall,
            "low_confidence": self.low_confidence,
            "calibrated": self.calibrated,
            "method": self.method,
        }


def jeffreys_recall(k: int, n: int) -> float:
    """Jeffreys-smoothed recall ``(k + 0.5) / (n + 1)`` (§25.17).

    The Beta(1/2, 1/2) prior keeps the result strictly inside ``(0, 1)``:
    ``jeffreys_recall(0, 0) == 0.5`` (neutral) and ``jeffreys_recall(3, 3) == 0.875``
    (below a naive ``1.0``). Полнота со сглаживанием Джеффриса.
    """
    return (float(k) + _JEFFREYS_ALPHA) / (float(n) + _JEFFREYS_PRIOR_MASS)


def calibrate_recall(
    gold: list[dict],
    extraction_results: list[dict],
    *,
    min_n: int = DEFAULT_MIN_N,
) -> list[CalibratedPrior]:
    """Calibrate per-modality recall against a gold set (§25.17).

    ``gold`` is a list of ``{"fact_id", "modality"}`` dicts (the эталон); a gold
    fact is *matched* when its ``fact_id`` appears in the ids of
    ``extraction_results``. For each modality: ``k`` = matched, ``n`` = group size,
    ``recall_raw = k / n`` (``0.0`` when ``n == 0``), ``recall`` is Jeffreys-smoothed,
    and ``low_confidence`` is ``n < min_n``. Results are sorted by modality; an
    empty ``gold`` yields ``[]``.
    """
    if not gold:
        return []

    extracted_ids = {r["fact_id"] for r in extraction_results if "fact_id" in r}

    # Group gold facts by modality, preserving membership for k / n counts.
    groups: dict[str, list[dict]] = {}
    for fact in gold:
        groups.setdefault(fact["modality"], []).append(fact)

    priors: list[CalibratedPrior] = []
    for modality in sorted(groups):
        facts = groups[modality]
        n = len(facts)
        k = sum(1 for f in facts if f["fact_id"] in extracted_ids)
        recall_raw = (k / n) if n else 0.0
        priors.append(
            CalibratedPrior(
                context_key=modality,
                modality=modality,
                k=k,
                n=n,
                recall_raw=recall_raw,
                recall=jeffreys_recall(k, n),
                low_confidence=n < min_n,
            )
        )
    return priors
