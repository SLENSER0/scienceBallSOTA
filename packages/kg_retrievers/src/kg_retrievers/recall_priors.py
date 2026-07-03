"""Extractor-recall priors from coverage telemetry (§25.10).

The absence-confidence layer (§25.11, :mod:`kg_retrievers.confidence_of_absence`)
needs a per-entity-type *recall* (полнота извлечения) estimate to tell a real
knowledge gap from mere non-extraction. This module derives those priors
empirically from the MetaStore's coverage telemetry (§25.5): for each
``target_type`` we take the observed hit-rate ``n_found / n_attempts`` and smooth
it toward a neutral prior with a Beta-style pseudo-count, so thinly-sampled types
don't swing to a hard 0 or 1.

    recall = (n_found + a) / (n_attempts + a + b)

where ``a = m * s`` and ``b = (1 - m) * s`` encode a prior mean ``m`` (the neutral
default recall, 0.7) worth ``s = prior_strength`` pseudo-observations. With **no**
attempts this collapses to ``m`` (the neutral fallback); as attempts accumulate the
estimate is pulled toward the empirical hit-rate. Because ``a > 0``, ``b > 0`` and
``0 <= n_found <= n_attempts``, the result is always strictly inside ``(0, 1)``.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.storage.base import CoverageStats, MetaStore, RecallPrior
from kg_retrievers.confidence_of_absence import DEFAULT_RECALL, ExtractorRecall

# Neutral prior mean (m): the recall we assume before we have any telemetry. Kept
# in lock-step with the absence layer's ``DEFAULT_RECALL`` (§25.10 / §25.11).
NEUTRAL_RECALL: float = DEFAULT_RECALL
# Pseudo-observations (s = a + b) worth of neutral prior mixed into every estimate.
DEFAULT_PRIOR_STRENGTH: float = 20.0
# Synthetic extractor label: ``coverage_stats`` merges every extractor per
# target_type, so a derived prior describes the aggregate extractor (§25.10).
DERIVED_EXTRACTOR: str = "aggregate"

_EPS = 1e-9


def _clamp_open(x: float, eps: float = _EPS) -> float:
    """Clamp ``x`` into the open interval ``(0, 1)`` (keeps the prior mean valid)."""
    return max(eps, min(float(x), 1.0 - eps))


def smoothed_recall(
    n_found: int,
    n_attempts: int,
    *,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
    prior_mean: float = NEUTRAL_RECALL,
) -> float:
    """Beta-smoothed recall ``(n_found + a) / (n_attempts + a + b)`` (§25.10).

    ``a = prior_mean * prior_strength`` and ``b = (1 - prior_mean) * prior_strength``.
    Zero attempts (and zero found) collapse to ``prior_mean``; with ``prior_strength``
    and ``0 <= n_found <= n_attempts`` the result is strictly inside ``(0, 1)``.
    """
    s = max(0.0, float(prior_strength))
    m = _clamp_open(prior_mean)
    a = m * s
    b = (1.0 - m) * s
    denom = float(n_attempts) + a + b
    if denom <= 0.0:  # prior_strength == 0 and no attempts → nothing to go on
        return m
    return (float(n_found) + a) / denom


@dataclass(frozen=True)
class DerivedPrior:
    """A recall prior derived from one ``CoverageStats`` row, with provenance (§25.10)."""

    target_type: str
    recall: float
    n_found: int
    n_attempts: int
    hit_rate: float
    prior_strength: float

    def to_recall_prior(self, *, extractor: str = DERIVED_EXTRACTOR) -> RecallPrior:
        """Project onto the persisted :class:`RecallPrior` (sample_size = n_attempts)."""
        return RecallPrior(
            extractor=extractor,
            target_type=self.target_type,
            recall=self.recall,
            sample_size=self.n_attempts,
        )

    def as_dict(self) -> dict:
        return {
            "target_type": self.target_type,
            "recall": self.recall,
            "n_found": self.n_found,
            "n_attempts": self.n_attempts,
            "hit_rate": self.hit_rate,
            "prior_strength": self.prior_strength,
        }


def _derive_one(stat: CoverageStats, prior_strength: float) -> DerivedPrior:
    recall = smoothed_recall(stat.n_found, stat.n_attempts, prior_strength=prior_strength)
    return DerivedPrior(
        target_type=stat.target_type,
        recall=recall,
        n_found=stat.n_found,
        n_attempts=stat.n_attempts,
        hit_rate=stat.hit_rate,
        prior_strength=float(prior_strength),
    )


def derive_prior_details(
    metastore: MetaStore, *, prior_strength: float = DEFAULT_PRIOR_STRENGTH
) -> list[DerivedPrior]:
    """Full derivation (recall + provenance) per ``target_type`` from telemetry (§25.10)."""
    return [_derive_one(stat, prior_strength) for stat in metastore.coverage_stats()]


def derive_recall_priors(
    metastore: MetaStore, *, prior_strength: float = DEFAULT_PRIOR_STRENGTH
) -> list[RecallPrior]:
    """Smoothed recall prior per ``target_type`` from coverage telemetry (§25.10).

    Reads :meth:`MetaStore.coverage_stats` and Beta-smooths each hit-rate toward the
    neutral prior; returns one :class:`RecallPrior` per target type (does not persist).
    """
    return [
        d.to_recall_prior() for d in derive_prior_details(metastore, prior_strength=prior_strength)
    ]


def persist_recall_priors(
    metastore: MetaStore, *, prior_strength: float = DEFAULT_PRIOR_STRENGTH
) -> list[RecallPrior]:
    """Derive and persist the recall priors via ``save_recall_prior`` (§25.10).

    Idempotent per ``(extractor, target_type)`` (the store UPSERTs). Returns the
    priors that were written so callers can inspect them without a re-read.
    """
    priors = derive_recall_priors(metastore, prior_strength=prior_strength)
    for prior in priors:
        metastore.save_recall_prior(prior)
    return priors


def to_extractor_recall(
    metastore: MetaStore, *, default: float = NEUTRAL_RECALL
) -> ExtractorRecall:
    """Build an :class:`ExtractorRecall` from the *persisted* priors (§25.10 / §25.11).

    Maps each persisted prior's ``target_type`` → ``recall`` into ``per_entity_type``,
    so :meth:`ExtractorRecall.for_property` resolves an entity-type recall for any
    property, falling back to ``default`` for unseen types. Call
    :func:`persist_recall_priors` first to populate the store.
    """
    per_entity_type = {prior.target_type: prior.recall for prior in metastore.get_recall_priors()}
    return ExtractorRecall(default=default, per_entity_type=per_entity_type)
