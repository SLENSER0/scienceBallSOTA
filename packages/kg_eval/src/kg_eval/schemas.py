"""[DE] Track-C benchmark contracts (spec §33, port of science_ball evals/schemas).

Dependency-light dataclasses shared by the synthetic dataset generator
(:mod:`kg_eval.datasets.synthetic`), the absence-classification scorer
(:mod:`kg_eval.absence_eval`), the calibration harness, and the report writer.
Pure stdlib, fully offline — no numpy, no graph store.

The one invariant the whole benchmark hinges on: ``abstain`` (and SOTA's
``covered``) are things the *system* may output but are **never** a reality of the
world, so a verdict of ``abstain`` / ``covered`` is never scored *correct* — it is
counted as coverage, not accuracy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# What the system MAY output. Superset of REALITIES: adds ``abstain`` (honest
# deferral) and SOTA's ``covered`` (an active observation that carries no numeric
# value — present-like, but never a ground-truth reality here).
VERDICTS: tuple[str, ...] = (
    "present",
    "covered",
    "genuine_gap",
    "possible_miss",
    "retracted",
    "abstain",
)
# Ground-truth reality classes — VERDICTS minus the system-only ``covered`` /
# ``abstain``. The world is never "abstain"; abstention is a system decision.
REALITIES: tuple[str, ...] = ("present", "genuine_gap", "possible_miss", "retracted")

# Each generation archetype pins the true reality of a (material, property) cell.
ARCHETYPE_LABEL: dict[str, str] = {
    "PRESENT_TABLE": "present",  # value in a document table row → extracted
    "PRESENT_CATALOG": "present",  # value in the catalog → extracted
    "TRUE_MISS": "possible_miss",  # value STATED in prose, no table/catalog → offline miss
    "FALSE_MISS": "genuine_gap",  # property NAMED in prose, no measurable value → not a miss
    "ABSENT": "genuine_gap",  # never appears anywhere → genuinely un-researched
    "RETRACTED": "retracted",  # extracted then soft-retracted
}


@dataclass
class AbsenceCell:
    """One labelled ``(material, property)`` cell of a benchmark dataset.

    The benchmark's whole point is the separation of ``measurable_in_source`` (is a
    measurable observation actually *stated* in a source?) from
    ``mentioned_in_source`` (is the property merely *named* in a document?). A
    mention-based verdict cannot tell ``FALSE_MISS`` (mentioned, not measurable →
    ``genuine_gap``) from ``TRUE_MISS`` (mentioned, measurable → ``possible_miss``).
    """

    material_id: str
    property_id: str
    archetype: str  # a key of ARCHETYPE_LABEL
    true_label: str  # one of REALITIES
    measurable_in_source: bool
    mentioned_in_source: bool
    source_modality: str | None  # "table_row" | "catalog_row" | "chunk" | None
    doc_id: str | None
    stated_value: float | None
    unit: str | None
    access_level: str = "internal"

    def key(self) -> str:
        return f"{self.material_id}|{self.property_id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AbsencePrediction:
    """One method's verdict for one cell, scored against the cell's true label."""

    material_id: str
    property_id: str
    method: str  # baseline name | "absence_confidence" | value-method | "..._calibrated"
    verdict: str  # one of VERDICTS
    p_extractor_missed: float
    p_truly_absent: float
    true_label: str  # one of REALITIES
    calibrated: bool = False

    @property
    def correct(self) -> bool:
        """Strict exact-match. ``abstain`` / ``covered`` are never a reality, so a
        verdict of either can NEVER be correct — they are scored as coverage."""
        return self.verdict == self.true_label

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["correct"] = self.correct  # the computed property is not in asdict
        return d


@dataclass
class GoldExtractionFact:
    """A fact that *should* be extractable from a document (Track-A semantic match).

    ``extractable_offline`` gates whether the offline pipeline is expected to
    recover the fact: ``False`` for prose-only facts that need the LLM extractor.
    """

    doc_id: str
    material_id: str
    property_id: str
    source_type: str  # document_table_row | catalog_row | document_text
    modality: str  # table_row | catalog_row | chunk
    stated_value: float | None
    unit: str | None = None
    regime: dict[str, Any] = field(default_factory=dict)
    baseline_value: float | None = None
    direction: str | None = None
    extractable_offline: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetManifest:
    """The ground truth a generated corpus carries alongside its graph."""

    name: str
    seed: int
    profile: str  # offline | live-llm | cached-llm
    cells: list[AbsenceCell] = field(default_factory=list)
    extraction_gold: list[GoldExtractionFact] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def label_histogram(self) -> dict[str, int]:
        """Count cells per REALITY (all four keys always present, even at zero)."""
        h = dict.fromkeys(REALITIES, 0)
        for c in self.cells:
            h[c.true_label] = h.get(c.true_label, 0) + 1
        return h

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "seed": self.seed,
            "profile": self.profile,
            "materials": list(self.materials),
            "properties": list(self.properties),
            "label_histogram": self.label_histogram(),
            "cells": [c.to_dict() for c in self.cells],
            "extraction_gold": [g.to_dict() for g in self.extraction_gold],
            "notes": list(self.notes),
        }
