"""Extraction schemas emitted by rule/LLM extractors (§9.4 / §24.6).

Every extraction object must carry a non-empty ``evidence_text`` span — the
"no source span → no graph fact" invariant (§3.3/§3.6). ``confidence`` is bounded
to ``[0, 1]``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    evidence_text: str = Field(min_length=1)

    @field_validator("evidence_text")
    @classmethod
    def _non_empty_span(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("evidence_text must be a non-empty source span")
        return v


class EntityExtract(_Base):
    """A mentioned entity (material, process, equipment, property, ...)."""

    text: str = Field(min_length=1)
    entity_type: str  # maps to a NodeLabel / domain NER label
    canonical_name: str | None = None
    lang: Literal["ru", "en", "mixed", "unknown"] = "unknown"
    span_start: int | None = None
    span_end: int | None = None


class NumericConstraintExtract(_Base):
    """A numeric value/range with unit, e.g. 'сульфаты ≤300 мг/л' (§24.4)."""

    parameter: str
    operator: Literal["<", "<=", ">", ">=", "=", "range", "approx"] = "="
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None


class MeasurementExtract(_Base):
    """A measured property value (§9.4)."""

    material: str | None = None
    property: str
    value: float | None = None
    value_raw: str | None = None
    unit: str | None = None
    condition: str | None = None
    effect_direction: Literal["increase", "decrease", "no_change"] | None = None


class ProcessingRegimeExtract(_Base):
    operation: str
    temperature_c: float | None = None
    time_h: float | None = None
    atmosphere: str | None = None
    other_parameters: dict[str, str] = Field(default_factory=dict)


class RelationExtract(_Base):
    """A typed relation between two entity surface forms (§24.6)."""

    subject: str
    predicate: str  # e.g. removes / applies_to / implemented_in / distributes_between
    object: str


class ClaimExtract(_Base):
    """A review/finding statement (§24.6): fact vs recommendation."""

    text: str = Field(min_length=1)
    claim_type: Literal["finding", "recommendation", "limitation", "comparison"] = "finding"
    polarity: Literal["recommended", "not_recommended", "neutral"] = "neutral"
    subjects: list[str] = Field(default_factory=list)


class ExperimentExtract(_Base):
    """A described experiment linking material→regime→measurement (§9.4)."""

    title: str | None = None
    materials: list[str] = Field(default_factory=list)
    regime: ProcessingRegimeExtract | None = None
    measurements: list[MeasurementExtract] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)


class DocumentExtraction(BaseModel):
    """Container returned by the LLM extractor for one chunk."""

    model_config = ConfigDict(extra="ignore")

    entities: list[EntityExtract] = Field(default_factory=list)
    relations: list[RelationExtract] = Field(default_factory=list)
    measurements: list[MeasurementExtract] = Field(default_factory=list)
    numeric_constraints: list[NumericConstraintExtract] = Field(default_factory=list)
    claims: list[ClaimExtract] = Field(default_factory=list)
    regimes: list[ProcessingRegimeExtract] = Field(default_factory=list)
