"""§15.14 gap-priority weights + banding config (pure python, no store access).

RU: Конфиг приоритизации пробелов (§15.14). Оборачивает веса четырёх сигналов из
§15.9 (``absence_confidence`` / ``importance`` / ``domain_criticality`` / ``novelty``)
вместе с порогами разбивки итогового скора на полосы «высокий / средний / низкий».
Чистый python-контейнер настройки (frozen dataclass): не трогает граф/стор, сам
скоринг живёт в ``gap_scoring.py`` (§15.9). Метод :meth:`GapPriorityConfig.band`
отображает скор в ``[0, 1]`` на строку ``high`` / ``medium`` / ``low``.
EN: Gap-priority config (§15.14). Bundles the weights of the four §15.9 signals
(``absence_confidence`` / ``importance`` / ``domain_criticality`` / ``novelty``)
with the thresholds that split the final score into ``high`` / ``medium`` / ``low``
bands. A pure python settings container (frozen dataclass): it touches no
store/graph (scoring lives in ``gap_scoring.py``, §15.9).

Builds ON :mod:`kg_retrievers.gap_scoring`: reuses :data:`COMPONENT_NAMES`,
:data:`DEFAULT_WEIGHTS` and :func:`gap_priority_score` (that module is not edited).
Kuzu note: custom node props are not queryable columns — callers RETURN base
columns and read the rest via ``get_node()`` before assembling the gap dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kg_retrievers.gap_scoring import (
    COMPONENT_NAMES,
    DEFAULT_WEIGHTS,
    gap_priority_score,
)

# --- Band labels (§15.14) ----------------------------------------------------
BAND_HIGH = "high"  # высокий приоритет
BAND_MEDIUM = "medium"  # средний приоритет
BAND_LOW = "low"  # низкий приоритет

# --- Threshold keys (§15.14) -------------------------------------------------
# Only the two upper cut-offs are stored; anything below ``medium`` is ``low``.
THRESHOLD_KEYS: tuple[str, ...] = ("high", "medium")

# --- Defaults ----------------------------------------------------------------
# Weights default to the §15.9 signal weights (sum 1.0) — see gap_scoring.py.
DEFAULT_GAP_PRIORITY_WEIGHTS: dict[str, float] = dict(DEFAULT_WEIGHTS)
# Band cut-offs mirror the §15.9 RU priority words (>=0.66 high, >=0.33 medium).
DEFAULT_GAP_PRIORITY_THRESHOLDS: dict[str, float] = {"high": 0.66, "medium": 0.33}


def _validate_weights(weights: dict[str, float]) -> None:
    """Reject empty / unknown / negative weights or an all-zero total (§15.14)."""
    if not weights:
        raise ValueError("weights must be a non-empty mapping")
    for name, value in weights.items():
        if name not in COMPONENT_NAMES:
            raise ValueError(f"unknown weight {name!r}; expected one of {list(COMPONENT_NAMES)}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"weight {name!r} must be a number, got {value!r}")
        if value < 0:
            raise ValueError(f"weight {name!r} must be >= 0, got {value!r}")
    if sum(float(v) for v in weights.values()) <= 0.0:
        raise ValueError("weights must sum to a positive value")


def _validate_thresholds(thresholds: dict[str, float]) -> None:
    """Require ordered ``high`` > ``medium`` cut-offs, each in ``[0, 1]`` (§15.14)."""
    for key in THRESHOLD_KEYS:
        if key not in thresholds:
            raise ValueError(f"thresholds must contain {key!r}")
    for key, value in thresholds.items():
        if key not in THRESHOLD_KEYS:
            raise ValueError(f"unknown threshold {key!r}; expected one of {list(THRESHOLD_KEYS)}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"threshold {key!r} must be a number, got {value!r}")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"threshold {key!r} must be in [0, 1], got {value!r}")
    if float(thresholds["high"]) <= float(thresholds["medium"]):
        raise ValueError(
            "thresholds must be ordered: high > medium, got "
            f"high={thresholds['high']!r}, medium={thresholds['medium']!r}"
        )


@dataclass(frozen=True)
class GapPriorityConfig:
    """Immutable gap-priority config (§15.14): signal ``weights`` + band ``thresholds``.

    ``weights`` maps a §15.9 signal name (a subset of :data:`COMPONENT_NAMES`) to a
    non-negative weight with a positive total; ``thresholds`` holds the ``high`` and
    ``medium`` band cut-offs in ``[0, 1]`` with ``high`` > ``medium``. Validation runs
    in :meth:`__post_init__`; the frozen instance owns private copies of both dicts.
    """

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_GAP_PRIORITY_WEIGHTS))
    thresholds: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_GAP_PRIORITY_THRESHOLDS)
    )

    def __post_init__(self) -> None:
        # Frozen dataclass: own private copies of the caller's dicts before validating.
        object.__setattr__(self, "weights", dict(self.weights))
        object.__setattr__(self, "thresholds", dict(self.thresholds))
        _validate_weights(self.weights)
        _validate_thresholds(self.thresholds)

    def band(self, score: float) -> str:
        """Map a priority score in ``[0, 1]`` to ``high`` / ``medium`` / ``low`` (§15.14).

        Cut-offs are inclusive lower bounds: ``score >= thresholds['high']`` → ``high``,
        ``score >= thresholds['medium']`` → ``medium``, otherwise ``low``.
        """
        value = float(score)
        if value >= self.thresholds["high"]:
            return BAND_HIGH
        if value >= self.thresholds["medium"]:
            return BAND_MEDIUM
        return BAND_LOW

    def score(self, gap: dict) -> float:
        """Priority of a gap in ``[0, 1]`` using this config's weights (§15.9 via §15.14).

        Delegates to :func:`kg_retrievers.gap_scoring.gap_priority_score`, so the
        renormalization and neutral-default rules of §15.9 apply unchanged.
        """
        return gap_priority_score(gap, weights=self.weights)

    def band_for(self, gap: dict) -> str:
        """Band label (``high`` / ``medium`` / ``low``) of a gap dict (§15.14)."""
        return self.band(self.score(gap))

    def as_dict(self) -> dict:
        """Plain-dict projection for config dump / round-trip (§15.14, house style)."""
        return {
            "weights": dict(self.weights),
            "thresholds": dict(self.thresholds),
        }

    @classmethod
    def from_dict(cls, d: dict) -> GapPriorityConfig:
        """Rebuild (and re-validate) from an :meth:`as_dict` projection (§15.14).

        Missing keys fall back to the module defaults (:data:`DEFAULT_GAP_PRIORITY_WEIGHTS`
        and :data:`DEFAULT_GAP_PRIORITY_THRESHOLDS`). Validation matches the constructor's,
        so a malformed dict raises ``ValueError``.
        """
        raw_weights = d.get("weights")
        weights = (
            dict(raw_weights) if raw_weights is not None else dict(DEFAULT_GAP_PRIORITY_WEIGHTS)
        )
        raw_thresholds = d.get("thresholds")
        thresholds = (
            dict(raw_thresholds)
            if raw_thresholds is not None
            else dict(DEFAULT_GAP_PRIORITY_THRESHOLDS)
        )
        return cls(weights=weights, thresholds=thresholds)


def default_gap_priority_config() -> GapPriorityConfig:
    """Canonical default config (§15.14): §15.9 weights + 0.66/0.33 band cut-offs.

    Uses :data:`DEFAULT_GAP_PRIORITY_WEIGHTS` (the §15.9 signal weights, sum 1.0) and
    :data:`DEFAULT_GAP_PRIORITY_THRESHOLDS`, so the returned instance is always valid.
    """
    return GapPriorityConfig()
