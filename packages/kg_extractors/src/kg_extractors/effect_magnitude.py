"""Effect magnitude banding for the rule extractor's property vocabulary (§6.6).

:mod:`kg_extractors.effect_delta` computes a signed percentage change and a
derived direction, but it never buckets that percentage into an *interpretable*
band. Reviewers and auto-generated summaries do not want a raw ``48.0 %`` — they
want to read "large increase". This module adds that missing layer: it maps the
absolute percentage change onto a small controlled vocabulary of magnitude
bands so downstream review/summary text stays uniform and hand-checkable.

Даёт интерпретируемую полосу величины эффекта (§6.6): абсолютное процентное
изменение раскладывается по управляемому словарю полос
(negligible/marginal/moderate/large/unknown), а направление берётся как
рост/спад/без изменений/неизвестно. Это слой поверх :mod:`effect_delta`,
удобный для обзоров и сводок.

The band is decided purely on ``abs(pct_change)`` against three ascending
thresholds; anything above the top threshold is ``large``. A change that lands
inside the ``negligible`` band is treated as ``no_change`` regardless of its
sign, so a trivial numeric drift never reads as a real increase/decrease. When
the baseline is zero the percentage is undefined (``None``) and both band and
direction collapse to ``unknown``.

Pure python — no dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Magnitude band vocabulary (§6.6) — ascending severity, plus ``unknown``.
BAND_NEGLIGIBLE = "negligible"
BAND_MARGINAL = "marginal"
BAND_MODERATE = "moderate"
BAND_LARGE = "large"
BAND_UNKNOWN = "unknown"

# Direction vocabulary — mirrors :mod:`effect_delta`, plus ``unknown``.
DIR_INCREASE = "increase"
DIR_DECREASE = "decrease"
DIR_NO_CHANGE = "no_change"
DIR_UNKNOWN = "unknown"

_BANDS = frozenset({BAND_NEGLIGIBLE, BAND_MARGINAL, BAND_MODERATE, BAND_LARGE, BAND_UNKNOWN})
_DIRECTIONS = frozenset({DIR_INCREASE, DIR_DECREASE, DIR_NO_CHANGE, DIR_UNKNOWN})


@dataclass(frozen=True)
class EffectMagnitude:
    """Banded magnitude of a baseline→value effect (§6.6).

    Полоса величины эффекта: процентное изменение, полоса и направление.

    ``pct_change`` is the signed relative change in percent, or ``None`` when the
    baseline is zero. ``band`` is one of the magnitude bands; ``direction`` is
    one of the direction labels.
    """

    pct_change: float | None
    band: str
    direction: str

    def __post_init__(self) -> None:
        if self.band not in _BANDS:
            raise ValueError(f"unknown band: {self.band!r}")
        if self.direction not in _DIRECTIONS:
            raise ValueError(f"unknown direction: {self.direction!r}")

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view for JSON/serialization / словарь для сериализации."""
        return asdict(self)


def classify_magnitude(
    baseline: float,
    value: float,
    negligible_max: float = 1.0,
    marginal_max: float = 5.0,
    moderate_max: float = 20.0,
) -> EffectMagnitude:
    """Band a baseline→value change by ``abs(pct_change)`` (§6.6).

    Раскладывает изменение по полосам величины и выводит направление.

    ``baseline == 0`` makes the percentage undefined, so ``pct_change`` is
    ``None`` and both band and direction are ``unknown``. Otherwise the absolute
    percentage change is compared against the three ascending thresholds; a
    change inside the ``negligible`` band reads as ``no_change`` regardless of
    sign, else the sign of ``value - baseline`` picks increase/decrease.
    """
    if baseline == 0:
        return EffectMagnitude(pct_change=None, band=BAND_UNKNOWN, direction=DIR_UNKNOWN)

    pct = (value - baseline) / baseline * 100.0
    magnitude = abs(pct)

    if magnitude <= negligible_max:
        band = BAND_NEGLIGIBLE
    elif magnitude <= marginal_max:
        band = BAND_MARGINAL
    elif magnitude <= moderate_max:
        band = BAND_MODERATE
    else:
        band = BAND_LARGE

    if band == BAND_NEGLIGIBLE:
        direction = DIR_NO_CHANGE
    elif value > baseline:
        direction = DIR_INCREASE
    else:
        direction = DIR_DECREASE

    return EffectMagnitude(pct_change=pct, band=band, direction=direction)
