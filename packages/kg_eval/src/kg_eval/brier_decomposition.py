"""Murphy's Brier-score decomposition — reliability/resolution/uncertainty (§18.8).

Pure-stdlib decomposition of the Brier score for ``(predicted_confidence, actual_label)``
pairs into the three additive Murphy terms (Murphy 1973). Confidence is a probability in
``[0.0, 1.0]``; the label is the boolean outcome. Predictions are partitioned into
equal-width bins over ``[0, 1]`` and, for each non-empty bin ``k`` with count ``n_k``,
mean forecast ``conf_k`` and observed frequency ``o_k``:

* **reliability** — ``Σ_k n_k (conf_k − o_k)² / N``: калибровочная ошибка, low is good.
* **resolution** — ``Σ_k n_k (o_k − ō)² / N``: how far bin outcomes spread from the base
  rate ``ō``, high is good (discrimination).
* **uncertainty** — ``ō(1 − ō)``: irreducible variance of the outcome, forecaster-agnostic.

The Brier score obeys the exact identity ``brier = reliability − resolution + uncertainty``
whenever forecasts are constant within each bin (Murphy's three-term form). ``brier`` is
stored as that combination.

Binning convention mirrors §23.25 calibration: equal-width bins where bin ``i`` covers
``[i/n_bins, (i+1)/n_bins)`` and a confidence of exactly ``1.0`` is clamped into the last
bin so no prediction is dropped. Empty bins contribute nothing to any term. Empty input is
a caller bug and raises ``ValueError`` — пустой вход недопустим.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BrierDecomposition:
    """Murphy decomposition of the Brier score for one prediction set (§18.8).

    ``n`` is the number of scored pairs, ``n_bins`` the equal-width bin count, and
    ``brier``/``reliability``/``resolution``/``uncertainty`` the additive terms with
    ``brier == reliability − resolution + uncertainty``.
    """

    n: int
    n_bins: int
    brier: float
    reliability: float
    resolution: float
    uncertainty: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "n_bins": self.n_bins,
            "brier": round(self.brier, 6),
            "reliability": round(self.reliability, 6),
            "resolution": round(self.resolution, 6),
            "uncertainty": round(self.uncertainty, 6),
        }


def _bin_index(confidence: float, n_bins: int) -> int:
    """Return the bin index for ``confidence``; ``1.0`` clamps to the last bin."""
    idx = int(confidence * n_bins)
    if idx >= n_bins:
        idx = n_bins - 1
    if idx < 0:
        idx = 0
    return idx


def brier_decomposition(
    pairs: Sequence[tuple[float, bool]], n_bins: int = 10
) -> BrierDecomposition:
    """Compute Murphy's Brier decomposition over equal-width bins (§18.8).

    Each pair is ``(predicted_confidence, actual_label)``. Returns reliability,
    resolution, uncertainty and their combination ``brier = reliability − resolution +
    uncertainty``. Raises ``ValueError`` on empty input or ``n_bins < 1``.
    """
    if not pairs:
        raise ValueError("brier_decomposition requires at least one (confidence, label) pair")
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")

    n = len(pairs)
    counts = [0] * n_bins
    conf_sums = [0.0] * n_bins
    hit_sums = [0] * n_bins
    total_hits = 0
    for confidence, label in pairs:
        idx = _bin_index(confidence, n_bins)
        hit = 1 if label else 0
        counts[idx] += 1
        conf_sums[idx] += confidence
        hit_sums[idx] += hit
        total_hits += hit

    base_rate = total_hits / n
    reliability = 0.0
    resolution = 0.0
    for k in range(n_bins):
        n_k = counts[k]
        if not n_k:
            continue
        conf_k = conf_sums[k] / n_k
        o_k = hit_sums[k] / n_k
        reliability += n_k * (conf_k - o_k) ** 2
        resolution += n_k * (o_k - base_rate) ** 2
    reliability /= n
    resolution /= n
    uncertainty = base_rate * (1.0 - base_rate)
    brier = reliability - resolution + uncertainty
    return BrierDecomposition(
        n=n,
        n_bins=n_bins,
        brier=brier,
        reliability=reliability,
        resolution=resolution,
        uncertainty=uncertainty,
    )
