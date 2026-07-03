"""Gold-based recall calibration with Jeffreys smoothing (§25.17).

Unlike :mod:`kg_retrievers.recall_priors` — which *beta-smooths* extractor recall
from live :class:`CoverageStats` telemetry — this module *calibrates* recall against
a curated **gold set** (эталонная выборка): a list of facts a human confirmed the
corpus contains, grouped by ``modality``. For each modality we count how many gold
facts the extractor actually recovered (``n_found``) out of the expected group size
(``n_expected``) and report a Jeffreys-smoothed recall estimate::

    recall = (n_found + 0.5) / (n_expected + 1)

The Jeffreys prior (Beta(1/2, 1/2)) keeps the estimate strictly inside ``(0, 1)``
and — crucially — gives a *sane* answer for a thinly-sampled or empty group: a
modality with **no** gold facts (``n_expected == 0``) collapses to the neutral
``0.5`` rather than an undefined ``0/0`` or a falsely-confident ``1.0``. The
un-smoothed hit-rate is preserved alongside as ``recall_raw`` so callers can see
both the raw (сырое) and the calibrated (откалиброванное) полнота извлечения.

This module is deliberately distinct from ``recall_calibration.py`` (which keys the
gold set on ``fact_id`` and adds a ``low_confidence`` flag): here matching is by a
content *fact-key* (subject/predicate/object) and the DTO carries ``n_expected`` /
``n_found`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Jeffreys prior Beta(1/2, 1/2): pseudo-counts added to successes and to the total.
_JEFFREYS_ALPHA: float = 0.5
_JEFFREYS_PRIOR_MASS: float = 1.0

# Ordered content fields that identify a fact when no explicit key is supplied.
# Одинаковый ключ факта используется и для gold, и для extracted (совпадение факта).
_FACT_KEY_FIELDS: tuple[str, ...] = ("subject", "predicate", "object")


def jeffreys_recall(k: int, n: int) -> float:
    """Jeffreys-smoothed recall ``(k + 0.5) / (n + 1)`` (§25.17).

    The Beta(1/2, 1/2) prior keeps the result strictly inside ``(0, 1)``:
    ``jeffreys_recall(0, 0) == 0.5`` (neutral) and ``jeffreys_recall(1, 1) == 0.75``
    (below a naive ``1.0``). Полнота со сглаживанием Джеффриса.
    """
    return (float(k) + _JEFFREYS_ALPHA) / (float(n) + _JEFFREYS_PRIOR_MASS)


@dataclass(frozen=True, slots=True)
class CalibratedRecall:
    """A gold-calibrated recall estimate for one modality (§25.17).

    Одна оценка полноты (recall), откалиброванная по эталонной выборке.

    ``recall_raw`` is the un-smoothed hit-rate ``n_found / n_expected``; ``recall``
    is the Jeffreys-smoothed ``(n_found + 0.5) / (n_expected + 1)``.
    """

    modality: str
    n_expected: int
    n_found: int
    recall_raw: float
    recall: float
    method: str = "gold_calibrated"
    calibrated: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict, exposing both raw and calibrated recall."""
        return {
            "modality": self.modality,
            "n_expected": self.n_expected,
            "n_found": self.n_found,
            "recall_raw": self.recall_raw,
            "recall": self.recall,
            "method": self.method,
            "calibrated": self.calibrated,
        }


def _fact_key(fact: dict) -> tuple:
    """Content key for a fact, ignoring ``modality`` (одинаковый ключ факта).

    Prefers an explicit ``fact_key`` / ``fact_id``; otherwise builds a tuple over
    the canonical subject/predicate/object fields; falls back to a sorted view of
    all non-``modality`` items so unusual fact shapes still match deterministically.
    """
    for explicit in ("fact_key", "fact_id"):
        if explicit in fact:
            return (explicit, fact[explicit])
    present = [f for f in _FACT_KEY_FIELDS if f in fact]
    if present:
        return tuple((f, fact[f]) for f in present)
    return tuple(sorted((k, v) for k, v in fact.items() if k != "modality"))


def calibrate_recall(
    gold: list[dict],
    extracted: list[dict],
) -> list[CalibratedRecall]:
    """Calibrate per-modality recall against a gold set (§25.17).

    ``gold`` is a list of fact dicts each carrying a ``modality`` plus content
    fields (the эталон); a gold fact is *found* when its :func:`_fact_key` appears
    in the keys of ``extracted``. For each modality: ``n_expected`` = group size,
    ``n_found`` = matched, ``recall_raw = n_found / n_expected`` (``0.0`` when
    ``n_expected == 0``), and ``recall`` is Jeffreys-smoothed. Results are sorted by
    modality; an empty ``gold`` yields ``[]``.
    """
    extracted_keys = {_fact_key(item) for item in extracted}

    groups: dict[str, list[dict]] = {}
    for fact in gold:
        groups.setdefault(fact["modality"], []).append(fact)

    out: list[CalibratedRecall] = []
    for modality in sorted(groups):
        facts = groups[modality]
        n_expected = len(facts)
        n_found = sum(1 for f in facts if _fact_key(f) in extracted_keys)
        recall_raw = (n_found / n_expected) if n_expected else 0.0
        out.append(
            CalibratedRecall(
                modality=modality,
                n_expected=n_expected,
                n_found=n_found,
                recall_raw=recall_raw,
                recall=jeffreys_recall(n_found, n_expected),
            )
        )
    return out
