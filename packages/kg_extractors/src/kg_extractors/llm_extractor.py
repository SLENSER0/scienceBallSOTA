"""LLM extraction (§6): richer entity/measurement/claim extraction from a chunk.

Uses an OSS model (ADR-0006) to fill a ``DocumentExtraction``. Every item must
carry an ``evidence_text`` quote (enforced by the schema). Used selectively —
rule extraction covers the whole corpus cheaply.
"""

from __future__ import annotations

from kg_common import get_logger
from kg_extractors.llm import get_llm
from kg_schema.extraction import (
    ClaimExtract,
    DocumentExtraction,
    EntityExtract,
    MeasurementExtract,
    RelationExtract,
)

_log = get_logger("llm_extractor")

SYSTEM = (
    "Ты — экстрактор знаний для горно-металлургической R&D базы. Из фрагмента "
    "текста извлеки сущности, числовые измерения, связи и выводы. Верни СТРОГО JSON:\n"
    '{"entities":[{"text":str,"entity_type":"Material|TechnologySolution|Equipment|'
    'Property|ProcessingRegime|Person|Lab","canonical_name":str,"evidence_text":str,'
    '"confidence":0..1}],'
    '"measurements":[{"material":str|null,"property":str,"value":number|null,"unit":str|null,'
    '"evidence_text":str,"confidence":0..1}],'
    '"relations":[{"subject":str,"predicate":str,"object":str,"evidence_text":str,'
    '"confidence":0..1}],'
    '"claims":[{"text":str,"claim_type":"finding|recommendation|limitation|comparison",'
    '"polarity":"recommended|not_recommended|neutral","evidence_text":str,"confidence":0..1}]}\n'
    "evidence_text — дословная цитата из фрагмента. Не выдумывай значения. "
    "Если ничего нет — верни пустые массивы."
)


def extract_llm(text: str, *, model: str | None = None) -> DocumentExtraction:
    doc = DocumentExtraction()
    if not text or len(text.strip()) < 40:
        return doc
    llm = get_llm()
    try:
        data = llm.complete_json(
            f"ФРАГМЕНТ:\n{text[:2500]}",
            system=SYSTEM,
            model=model or llm._settings.llm_model_extract,
            max_tokens=1400,
        )
    except Exception as exc:
        _log.warning("llm_extract.failed", error=str(exc)[:120])
        return doc
    if not isinstance(data, dict):
        return doc

    for e in data.get("entities", []) or []:
        _try(doc.entities, EntityExtract, e, {"text", "entity_type"})
    for m in data.get("measurements", []) or []:
        _try(doc.measurements, MeasurementExtract, m, {"property"})
    for r in data.get("relations", []) or []:
        _try(doc.relations, RelationExtract, r, {"subject", "predicate", "object"})
    for c in data.get("claims", []) or []:
        _try(doc.claims, ClaimExtract, c, {"text"})
    return doc


def _try(target: list, model_cls, row: dict, required: set[str]) -> None:  # type: ignore[no-untyped-def]
    if not isinstance(row, dict) or not all(row.get(k) for k in required):
        return
    row.setdefault("evidence_text", row.get("text") or " ".join(str(row.get(k)) for k in required))
    if not str(row.get("evidence_text", "")).strip():
        return
    try:
        target.append(model_cls(**{k: row.get(k) for k in model_cls.model_fields if k in row}))
    except Exception:  # skip invalid rows
        return
