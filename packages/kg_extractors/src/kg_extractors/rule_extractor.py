"""Rule-based extraction (§6): taxonomy entities + numeric measurements from text.

Fast and free (no LLM) — runs on every chunk of the corpus. Produces a
``DocumentExtraction`` with evidence spans, so it satisfies the evidence-first
invariant on its own; the LLM extractor enriches selected chunks.
"""

from __future__ import annotations

import functools
import re

from kg_extractors.query_parser import scan_taxonomy
from kg_extractors.units import parse_numeric_constraints
from kg_schema.extraction import (
    DocumentExtraction,
    EntityExtract,
    MeasurementExtract,
)
from kg_schema.taxonomy import load_taxonomy

_SENT = re.compile(r"[^.!?\n]*[.!?\n]")


@functools.lru_cache(maxsize=1)
def _unit_to_property() -> dict[str, str]:
    """Map a canonical unit → property id (from the properties taxonomy default_unit)."""
    idx = load_taxonomy()
    out: dict[str, str] = {}
    for e in idx.entries:
        if e.node_type == "Property" and e.default_unit:
            out.setdefault(e.default_unit, e.id)
    return out


def _window(text: str, span: str, radius: int = 120) -> str:
    pos = text.find(span)
    if pos < 0:
        return span
    start = max(0, pos - radius)
    end = min(len(text), pos + len(span) + radius)
    return text[start:end].strip()


def extract_rules(text: str) -> DocumentExtraction:
    doc = DocumentExtraction()
    if not text or len(text) < 20:
        return doc

    entities = scan_taxonomy(text)
    materials = [e for e in entities if e.node_type == "Material"]
    for e in entities:
        term = e.canonical_ru or e.canonical_en
        doc.entities.append(
            EntityExtract(
                text=term,
                entity_type=e.node_type,
                canonical_name=e.id,
                lang="ru" if re.search(r"[а-яё]", term, re.I) else "en",
                confidence=0.7,
                evidence_text=_window(text, term, 80) or term,
            )
        )

    u2p = _unit_to_property()
    for c in parse_numeric_constraints(text):
        unit = c.normalized_unit or c.unit
        if not unit:
            continue
        prop = u2p.get(c.normalized_unit or "", "concentration")
        val = c.normalized_value if c.normalized_value is not None else c.value
        if val is None and c.normalized_min is not None:
            val = (c.normalized_min + (c.normalized_max or c.normalized_min)) / 2
        material = materials[0].id if materials else None
        try:
            doc.measurements.append(
                MeasurementExtract(
                    material=material,
                    property=prop,
                    value=val,
                    value_raw=c.source_span,
                    unit=unit,
                    confidence=0.6,
                    evidence_text=_window(text, c.source_span) or c.source_span,
                )
            )
        except Exception:  # skip malformed
            continue
        doc.numeric_constraints.append(_to_numeric(c, text))
    return doc


def _to_numeric(c, text):  # type: ignore[no-untyped-def]
    from kg_schema.extraction import NumericConstraintExtract

    return NumericConstraintExtract(
        parameter=c.normalized_unit or c.unit or "value",
        operator=c.operator
        if c.operator in {"<", "<=", ">", ">=", "=", "range", "approx"}
        else "=",
        value=c.value,
        min=c.min,
        max=c.max,
        unit=c.unit,
        confidence=0.6,
        evidence_text=_window(text, c.source_span) or c.source_span,
    )
