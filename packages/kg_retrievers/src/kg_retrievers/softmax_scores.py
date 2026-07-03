"""Temperature-scaled softmax over raw retrieval scores (§12.4 Weighted fusion / RRF).

Softmax-нормализатор с температурой: сырые score → распределение вероятностей.
Temperature-scaled softmax converting raw retrieval scores into a probability
distribution. Complements ``score_normalization`` (min-max / z-score only) with a
proper score→probability normalizer plus Shannon entropy in nats.

- **softmax_normalize** — численно устойчивый softmax (вычесть max перед exp);
  температура T масштабирует «остроту»: большая T → почти равномерно, малая T →
  пик на максимуме. Numerically stable: subtracts the max before ``exp`` so huge
  scores (e.g. 1000/1001) never overflow.
- **to_distribution** — то же плюс энтропия Шеннона в натах / same plus Shannon
  entropy in nats, wrapped in a frozen :class:`SoftmaxResult`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SoftmaxResult:
    """Результат softmax / probability distribution tagged with its temperature."""

    temperature: float
    probs: dict[str, float]
    entropy: float

    def as_dict(self) -> dict[str, Any]:
        """Сериализуемое представление / serializable ``{temperature, probs, entropy}``."""
        return {
            "temperature": self.temperature,
            "probs": dict(self.probs),
            "entropy": self.entropy,
        }


def softmax_normalize(scores: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
    """Temperature-scaled softmax → probabilities summing to 1.0; empty → ``{}``.

    Numerically stable: the maximum scaled score is subtracted before ``exp`` so
    even very large raw scores (``{a: 1000, b: 1001}``) yield finite outputs. A
    larger ``temperature`` flattens the distribution toward uniform; a smaller
    one sharpens it toward the argmax. ``temperature`` must be strictly positive.
    """
    if temperature <= 0.0:
        raise ValueError("temperature must be strictly positive")
    if not scores:
        return {}
    keys = list(scores.keys())
    scaled = [float(scores[k]) / temperature for k in keys]
    top = max(scaled)
    exps = [math.exp(s - top) for s in scaled]
    total = math.fsum(exps)
    return {k: e / total for k, e in zip(keys, exps, strict=True)}


def to_distribution(scores: dict[str, float], temperature: float = 1.0) -> SoftmaxResult:
    """Softmax distribution plus Shannon entropy (nats); empty → ``{}`` and 0.0.

    Entropy is ``-Σ p·ln p`` in nats (terms with ``p == 0`` contribute 0). A
    single-element input yields probability 1.0 and entropy 0.0; a uniform
    distribution of size ``n`` has entropy ``ln(n)``.
    """
    probs = softmax_normalize(scores, temperature)
    entropy = -math.fsum(p * math.log(p) for p in probs.values() if p > 0.0)
    return SoftmaxResult(temperature=float(temperature), probs=probs, entropy=entropy)
