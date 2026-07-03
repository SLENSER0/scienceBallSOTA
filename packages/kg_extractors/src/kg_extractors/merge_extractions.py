"""Extraction merge/dedup + confidence fusion — the §6.13 orchestrator.

The orchestrator collects ``DocumentExtraction`` objects emitted by the rule,
LLM and ML extractors (§6.13) and folds them into a single, de-duplicated
extraction.  Where the rule extractor's naive ``_merge`` simply concatenated
every list, this module collapses repeated facts and *fuses* their confidences
with a noisy-OR, so independent extractors that agree reinforce one another
instead of emitting duplicate graph facts.

RU: слияние извлечений / показатель уверенности — EN: extraction merge /
confidence.

Dedup keys:

* entities — ``canonical_name`` (RU: каноническое имя), else the lowercased
  surface ``text`` (§6.13);
* measurements — ``(property, normalized value, unit)`` (§9.4).

Confidence fusion is noisy-OR: ``1 - Π(1 - cᵢ)`` — the probability that *at
least one* extractor is right.  Two agreeing extractors at 0.6 and 0.7 fuse to
0.88.  Provenance (evidence spans, ``value_raw``, material, character offsets)
is preserved by keeping the source item with the longest ``evidence_text`` as
the representative and overriding only its confidence.
"""

from __future__ import annotations

from collections.abc import Iterable

from kg_schema.extraction import (
    DocumentExtraction,
    EntityExtract,
    MeasurementExtract,
)

#: Decimals kept when rounding fused confidences (stable, hand-checkable keys).
_CONFIDENCE_DECIMALS = 6
#: Decimals used to normalize measurement values before keying (float noise).
_VALUE_DECIMALS = 6


def _clamp01(value: float) -> float:
    """Clamp ``value`` into the ``[0, 1]`` confidence interval (§9.4)."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def fuse_confidence(values: Iterable[float]) -> float:
    """Fuse independent confidences with a noisy-OR (§6.13).

    Computes ``1 - Π(1 - cᵢ)`` — the probability that at least one extractor is
    correct.  Empty input fuses to ``0.0``; a single value passes through
    unchanged.  Each input is clamped to ``[0, 1]`` and the result is rounded to
    keep fused values stable and hand-checkable (e.g. ``0.6, 0.7 -> 0.88``).
    """
    product = 1.0
    seen = False
    for value in values:
        seen = True
        product *= 1.0 - _clamp01(float(value))
    if not seen:
        return 0.0
    return round(_clamp01(1.0 - product), _CONFIDENCE_DECIMALS)


def _entity_key(entity: EntityExtract) -> str:
    """Dedup key for an entity: ``canonical_name`` else lowercased ``text``."""
    if entity.canonical_name:
        return f"canon::{entity.canonical_name}"
    return f"text::{entity.text.strip().lower()}"


def _norm_value(value: float | None) -> float | None:
    """Normalize a measurement value for keying (round away float noise)."""
    return None if value is None else round(float(value), _VALUE_DECIMALS)


def _measurement_key(m: MeasurementExtract) -> tuple[str, float | None, str]:
    """Dedup key for a measurement: ``(property, normalized value, unit)``."""
    return (m.property.strip(), _norm_value(m.value), (m.unit or "").strip())


def _fuse_entities(entities: list[EntityExtract]) -> list[EntityExtract]:
    """Collapse duplicate entities, fusing confidence via noisy-OR (§6.13).

    Groups preserve first-seen order; the representative is the item with the
    longest ``evidence_text`` (richest provenance), with only its confidence
    overridden by the fused value.
    """
    order: list[str] = []
    groups: dict[str, list[EntityExtract]] = {}
    for entity in entities:
        key = _entity_key(entity)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(entity)

    out: list[EntityExtract] = []
    for key in order:
        items = groups[key]
        base = max(items, key=lambda e: len(e.evidence_text))
        fused = fuse_confidence(item.confidence for item in items)
        out.append(base.model_copy(update={"confidence": fused}))
    return out


def _fuse_measurements(measurements: list[MeasurementExtract]) -> list[MeasurementExtract]:
    """Collapse duplicate measurements, fusing confidence via noisy-OR (§9.4).

    Duplicates share ``(property, normalized value, unit)``.  The representative
    keeps the longest ``evidence_text`` so the source span is preserved.
    """
    order: list[tuple[str, float | None, str]] = []
    groups: dict[tuple[str, float | None, str], list[MeasurementExtract]] = {}
    for m in measurements:
        key = _measurement_key(m)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(m)

    out: list[MeasurementExtract] = []
    for key in order:
        items = groups[key]
        base = max(items, key=lambda m: len(m.evidence_text))
        fused = fuse_confidence(item.confidence for item in items)
        out.append(base.model_copy(update={"confidence": fused}))
    return out


def merge_extractions(extractions: list[DocumentExtraction]) -> DocumentExtraction:
    """Merge many per-extractor extractions into one de-duplicated result (§6.13).

    Entities and measurements are de-duplicated with fused (noisy-OR)
    confidence; relations, numeric constraints, claims and regimes are preserved
    (concatenated in order) so no provenance is lost.  An empty list yields an
    empty ``DocumentExtraction``; a single extraction passes through with
    duplicates (if any) collapsed.
    """
    merged = DocumentExtraction()
    if not extractions:
        return merged

    all_entities: list[EntityExtract] = []
    all_measurements: list[MeasurementExtract] = []
    for doc in extractions:
        all_entities.extend(doc.entities)
        all_measurements.extend(doc.measurements)
        merged.relations.extend(doc.relations)
        merged.numeric_constraints.extend(doc.numeric_constraints)
        merged.claims.extend(doc.claims)
        merged.regimes.extend(doc.regimes)

    merged.entities = _fuse_entities(all_entities)
    merged.measurements = _fuse_measurements(all_measurements)
    return merged
