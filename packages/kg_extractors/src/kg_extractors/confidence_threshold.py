"""§16.5 Rule ``low_confidence`` — per-source-type / per-property threshold resolver.

The ``low_confidence`` validation rule (правило низкой уверенности, §16.5) flags a
proposed fact whose extraction confidence (показатель уверенности) falls below a
threshold (порог). That threshold is not global: it is resolved per **source type**
(тип источника — e.g. ``table``, ``text``, ``figure``) and per **property**
(свойство — e.g. ``value``, ``unit``), so a noisy source or a hard-to-extract
property can demand more confidence than the default.

Resolution picks the **most specific** override (наиболее конкретное правило):

* a ``by_property`` override wins over
* a ``by_source`` override, which wins over
* the ``default`` threshold.

Property beats source on conflict (свойство важнее источника): if both a source-type
and a property override exist, the property override is used.

:func:`resolve_threshold` returns the resolved threshold; :func:`is_low_confidence`
compares a confidence against it and returns a frozen :class:`ThresholdDecision`
whose ``below`` is ``True`` iff ``confidence < threshold`` (a confidence exactly on
the boundary is **not** low). Pure Python — no LLM, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

#: Default threshold (порог по умолчанию) when no override matches (§16.5).
DEFAULT_THRESHOLD = 0.65


@dataclass(frozen=True)
class ThresholdDecision:
    """Outcome of the ``low_confidence`` check for one fact (§16.5).

    Fields
    ------
    confidence
        The fact's extraction confidence (показатель уверенности), ``[0, 1]``.
    threshold
        The resolved threshold (порог) — echoes :func:`resolve_threshold`.
    below
        ``True`` iff ``confidence < threshold`` (уверенность ниже порога). A
        confidence exactly equal to the threshold is **not** below.
    source_type
        The source type (тип источника) the threshold was resolved for.
    property_name
        The property (свойство) the threshold was resolved for.
    """

    confidence: float
    threshold: float
    below: bool
    source_type: str
    property_name: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all five fields, JSON-friendly)."""
        return {
            "confidence": self.confidence,
            "threshold": self.threshold,
            "below": self.below,
            "source_type": self.source_type,
            "property_name": self.property_name,
        }


@dataclass(frozen=True)
class ThresholdConfig:
    """Threshold configuration for the ``low_confidence`` rule (§16.5).

    Fields
    ------
    default
        Fallback threshold (порог по умолчанию) used when no override matches.
    by_source
        Per-source-type overrides (переопределения по типу источника), mapping a
        source type (e.g. ``"table"``) to its threshold.
    by_property
        Per-property overrides (переопределения по свойству), mapping a property
        name (e.g. ``"value"``) to its threshold. These beat ``by_source``.
    """

    default: float = DEFAULT_THRESHOLD
    by_source: Mapping[str, float] = field(default_factory=dict)
    by_property: Mapping[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all three fields, JSON-friendly)."""
        return {
            "default": self.default,
            "by_source": dict(self.by_source),
            "by_property": dict(self.by_property),
        }


def resolve_threshold(cfg: ThresholdConfig, source_type: str, property_name: str) -> float:
    """Resolve the most specific threshold for *source_type* / *property_name* (§16.5).

    Precedence (порядок приоритета): a ``by_property`` override wins over a
    ``by_source`` override, which wins over ``default``. Property beats source on
    conflict (свойство важнее источника).

    Examples (hand-checked): with a default config ``resolve_threshold(cfg,
    "table", "x") -> 0.65``; with ``by_source={"table": 0.8}`` a ``table`` source
    resolves to ``0.8``; with ``by_property={"value": 0.9}`` the property
    ``"value"`` resolves to ``0.9`` even when a ``by_source`` override also matches.
    """
    if property_name in cfg.by_property:
        return cfg.by_property[property_name]
    if source_type in cfg.by_source:
        return cfg.by_source[source_type]
    return cfg.default


def is_low_confidence(
    cfg: ThresholdConfig,
    confidence: float,
    source_type: str,
    property_name: str,
) -> ThresholdDecision:
    """Decide whether *confidence* is below the resolved threshold (§16.5).

    Resolves the threshold via :func:`resolve_threshold`, then sets ``below`` iff
    ``confidence < threshold``. A confidence exactly equal to the threshold
    (граничный случай) is **not** low. The returned ``threshold`` echoes the
    resolver so callers can report why a fact was (or was not) flagged.

    Examples (hand-checked): with the default threshold ``0.65``,
    ``is_low_confidence(cfg, 0.7, "table", "x").below`` is ``False`` while
    ``is_low_confidence(cfg, 0.5, "table", "x").below`` is ``True``.
    """
    threshold = resolve_threshold(cfg, source_type, property_name)
    below = float(confidence) < threshold
    return ThresholdDecision(
        confidence=confidence,
        threshold=threshold,
        below=below,
        source_type=source_type,
        property_name=property_name,
    )
