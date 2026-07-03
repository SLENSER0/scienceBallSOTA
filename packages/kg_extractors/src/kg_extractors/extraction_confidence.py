"""§6.16 combine multi-extractor confidences — layered confidence fusion.

Each fact may be proposed by up to three extraction *layers* (§6.16): the rule
extractor (правило), the ML/NER model (модель) and the LLM (языковая модель).
Each reports its own confidence (показатель уверенности) in ``[0, 1]``. This
module fuses whichever layers fired into a single :class:`CombinedConfidence`.

Two fusion methods (метод слияния) are offered:

* **weighted mean** (взвешенное среднее) — the default; ``Σ wᵢ·cᵢ / Σ wᵢ`` over
  the present layers, with per-layer ``weights`` (defaulting to equal weight);
* **noisy-OR** (шумное ИЛИ) — ``1 - Π(1 - cᵢ)``, the probability that *at least
  one* independent layer is right (:func:`noisy_or`).

On top of either method an **agreement boost** (бонус согласия) is applied when
``>= 2`` layers agree — i.e. are present and their confidences all lie within a
tolerance of one another (:func:`agreement_boost`). Independent extractors that
concur reinforce the fused confidence, nudging it toward ``1.0``; layers that
disagree (spread beyond the tolerance) receive no boost.

Everything is clamped to ``[0, 1]`` and rounded so fused values stay stable and
hand-checkable. Pure Python — no LLM, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

#: Decimals kept when rounding fused confidences (stable, hand-checkable keys).
_CONFIDENCE_DECIMALS = 6

# --- extraction layers (слои извлечения, §6.16) -------------------------------
LAYER_RULE = "rule"  # правило
LAYER_ML = "ml"  # ML / NER модель
LAYER_LLM = "llm"  # языковая модель

#: Canonical layer order — drives ``sources`` ordering in the result.
LAYER_ORDER: tuple[str, ...] = (LAYER_RULE, LAYER_ML, LAYER_LLM)

# --- fusion methods (методы слияния, §6.16) -----------------------------------
METHOD_WEIGHTED_MEAN = "weighted_mean"  # взвешенное среднее (default)
METHOD_NOISY_OR = "noisy_or"  # шумное ИЛИ

VALID_METHODS: frozenset[str] = frozenset({METHOD_WEIGHTED_MEAN, METHOD_NOISY_OR})

#: Default weight for a layer absent from an explicit ``weights`` map.
DEFAULT_WEIGHT = 1.0
#: Fraction of the gap to ``1.0`` closed per agreeing layer beyond the first.
DEFAULT_AGREEMENT_BOOST = 0.1
#: Max spread among present confidences still counted as agreement (§6.16).
DEFAULT_AGREEMENT_TOL = 0.25


@dataclass(frozen=True)
class CombinedConfidence:
    """Fused confidence over the extraction layers that fired (§6.16).

    Fields
    ------
    value
        Fused confidence in ``[0, 1]`` (показатель уверенности) after applying
        the chosen fusion method and any agreement boost.
    sources
        Names of the contributing layers in canonical order
        (:data:`LAYER_ORDER`) — which layers fired (rule / ml / llm).
    method
        The fusion method used (:data:`METHOD_WEIGHTED_MEAN` /
        :data:`METHOD_NOISY_OR`).
    """

    value: float
    sources: list[str] = field(default_factory=list)
    method: str = METHOD_WEIGHTED_MEAN

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all three fields, JSON-friendly)."""
        return {
            "value": self.value,
            "sources": list(self.sources),
            "method": self.method,
        }


def _clamp01(value: float) -> float:
    """Clamp *value* into the ``[0, 1]`` confidence interval (§6.16)."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def noisy_or(confidences: Iterable[float]) -> float:
    """Fuse independent confidences with a noisy-OR — ``1 - Π(1 - cᵢ)`` (§6.16).

    This is the probability that *at least one* independent layer is right. Empty
    input fuses to ``0.0``; a single value passes through unchanged. Each input is
    clamped to ``[0, 1]`` and the result rounded (e.g. ``[0.5, 0.5] -> 0.75``).
    """
    product = 1.0
    seen = False
    for conf in confidences:
        seen = True
        product *= 1.0 - _clamp01(float(conf))
    if not seen:
        return 0.0
    return round(_clamp01(1.0 - product), _CONFIDENCE_DECIMALS)


def agreement_boost(
    value: float,
    n_agree: int,
    *,
    boost: float = DEFAULT_AGREEMENT_BOOST,
) -> float:
    """Nudge *value* toward ``1.0`` when ``n_agree >= 2`` layers agree (§6.16).

    Each agreeing layer beyond the first closes a ``boost`` fraction of the gap to
    ``1.0``: ``value + boost·(n_agree - 1)·(1 - value)``. With fewer than two
    agreeing layers *value* is returned unchanged (only clamped). The result is
    clamped to ``[0, 1]`` and rounded — e.g. ``agreement_boost(0.6, 2) -> 0.64``.
    """
    if n_agree < 2:
        return round(_clamp01(value), _CONFIDENCE_DECIMALS)
    factor = boost * (n_agree - 1)
    boosted = value + factor * (1.0 - value)
    return round(_clamp01(boosted), _CONFIDENCE_DECIMALS)


def _weighted_mean(present: dict[str, float], weights: dict[str, float] | None) -> float:
    """Weighted mean ``Σ wᵢ·cᵢ / Σ wᵢ`` over *present* layers (§6.16).

    Missing or ``None`` weights default to :data:`DEFAULT_WEIGHT`; negative
    weights are floored to ``0``. If every weight vanishes, falls back to a plain
    (equal-weight) mean so the result is always well defined.
    """
    total_w = 0.0
    acc = 0.0
    for name, conf in present.items():
        raw = weights.get(name, DEFAULT_WEIGHT) if weights else DEFAULT_WEIGHT
        weight = max(0.0, float(raw))
        acc += weight * conf
        total_w += weight
    if total_w <= 0.0:  # all weights zero — degrade to a plain mean
        return sum(present.values()) / len(present)
    return acc / total_w


def combine_layers(
    rule: float | None = None,
    ml: float | None = None,
    llm: float | None = None,
    *,
    weights: dict[str, float] | None = None,
    method: str = METHOD_WEIGHTED_MEAN,
    boost: float = DEFAULT_AGREEMENT_BOOST,
    agreement_tol: float = DEFAULT_AGREEMENT_TOL,
) -> CombinedConfidence:
    """Fuse the rule / ml / llm layer confidences into one score (§6.16).

    Only the layers whose confidence is not ``None`` contribute. Their clamped
    confidences are fused by *method* — weighted mean (default,
    :data:`METHOD_WEIGHTED_MEAN`) or noisy-OR (:data:`METHOD_NOISY_OR`) — then, if
    ``>= 2`` layers agree (present with spread ``<= agreement_tol``), an
    :func:`agreement_boost` nudges the value up. With no layers present the value
    is ``0.0`` and ``sources`` empty. A single layer passes through unchanged.

    Examples (hand-checked): ``combine_layers(ml=0.7)`` → ``0.7``;
    ``combine_layers(rule=0.6, ml=0.6)`` → ``0.64`` (agreement boost);
    ``combine_layers(rule=0.4, ml=0.9, weights={"rule": 1, "ml": 3})`` → ``0.775``.
    """
    if method not in VALID_METHODS:
        raise ValueError(f"unknown fusion method / неизвестный метод: {method!r}")

    raw: dict[str, float | None] = {LAYER_RULE: rule, LAYER_ML: ml, LAYER_LLM: llm}
    # Keep canonical order; clamp each present layer into [0, 1].
    present: dict[str, float] = {
        name: _clamp01(float(value)) for name, value in raw.items() if value is not None
    }
    sources = list(present.keys())
    if not present:
        return CombinedConfidence(value=0.0, sources=[], method=method)

    values = list(present.values())
    base = noisy_or(values) if method == METHOD_NOISY_OR else _weighted_mean(present, weights)

    # Agreement: >= 2 layers present whose confidences all lie within the
    # tolerance (they concur rather than conflict) → reinforce the fused value.
    if len(values) >= 2 and (max(values) - min(values)) <= agreement_tol:
        base = agreement_boost(base, len(values), boost=boost)

    value = round(_clamp01(base), _CONFIDENCE_DECIMALS)
    return CombinedConfidence(value=value, sources=sources, method=method)
