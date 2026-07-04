"""Full schema-guided ``ExperimentExtract`` LLM extractor (§6.9).

Полный LLM-экстрактор эксперимента со схемо-ориентированным выводом.

This module implements the §6.9 acceptance criterion that the older
:mod:`kg_extractors.llm_extractor` only partly covered:

* **Complete ``ExperimentExtract``** — one described experiment as
  ``material_mentions`` / ``processing[]`` / ``measurements[]`` /
  ``equipment_mentions[]`` / ``lab_mentions[]`` / ``claims[]`` (§9.4). Regimes and
  measurements reuse the canonical Pydantic models from
  :mod:`kg_schema.extraction` (``ProcessingRegimeExtract`` / ``MeasurementExtract``)
  — no schema is re-invented here.

* **Claim vs Finding (§8.1)** — each ``claims[]`` element is a
  :class:`ClaimFinding` with an explicit ``claim_type ∈ {claim, finding}`` plus
  mention references ``about_material`` / ``about_property`` / ``about_regime`` (for
  the later ``(:Claim)-[:ABOUT_MATERIAL|ABOUT_PROPERTY|ABOUT_REGIME]->`` edges,
  §8.2). A *finding* is an empirically observed/measured result; a *claim* is a
  general assertion, hypothesis or recommendation. When the model omits or garbles
  the label we derive it deterministically from the rule cue-word classifier
  (:func:`kg_extractors.claim_classifier.classify_claim`) — reused, not
  re-implemented — so the distinction survives a weak model, and we keep the finer
  4-way ``fine_class`` + agreement flag as a review signal.

* **retry / repair of invalid JSON (§6.9)** — the extractor calls the LLM in JSON
  mode and, on a non-JSON reply *or* a Pydantic ``ValidationError``, re-prompts the
  model with the concrete error (bounded ``max_repairs``). After the budget is
  exhausted it performs a **controlled drop** (empty result + log), never a crash.
  Facts whose ``evidence_text`` is empty are dropped up front — the "no span → no
  fact" invariant (§9.2 Step 4 / §6.10).

Pure and side-effect-free: no graph reads, no writes, no network of its own — the
LLM client is injected (any object exposing ``complete(user, *, system, model,
max_tokens) -> str``) or lazily built via :func:`kg_extractors.llm.get_llm`, so the
whole path (including both repair and controlled-drop branches) is unit-testable
with a stub and no OpenRouter key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from kg_common import get_logger
from kg_extractors.claim_classifier import classify_claim
from kg_extractors.llm import _try_parse_json, get_llm
from kg_schema.extraction import MeasurementExtract, ProcessingRegimeExtract

_log = get_logger("experiment_extractor")

# Minimum characters worth an LLM call — below this a chunk is boilerplate.
_MIN_CHARS = 40
# Cap on characters sent to the model per chunk (bounds a giant paragraph).
_MAX_PROMPT_CHARS = 3000
_NUM = re.compile(r"\d")

ClaimType = Literal["claim", "finding"]
FineClass = Literal["finding", "recommendation", "limitation", "comparison"]


# --------------------------------------------------------------------------- #
# Claim vs Finding (§8.1)                                                      #
# --------------------------------------------------------------------------- #
class ClaimFinding(BaseModel):
    """A single claim/finding statement with the §8.1 claim-vs-finding split.

    ``claim_type`` distinguishes an empirical *finding* from a general *claim*;
    ``about_*`` are surface-form mention references for the later ABOUT_* edges.
    """

    model_config = ConfigDict(extra="ignore")

    statement: str = Field(min_length=1)
    claim_type: ClaimType = "claim"
    about_material: str | None = None
    about_property: str | None = None
    about_regime: str | None = None
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    # Deterministic rule cross-check (§6.9) — review/explainability only.
    fine_class: FineClass | None = None
    rule_agrees: bool | None = None

    @field_validator("evidence_text", "statement")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be a non-empty span")
        return v


class FullExperimentExtract(BaseModel):
    """One described experiment (§9.4) — the complete §6.9 shape."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    material_mentions: list[str] = Field(default_factory=list)
    processing: list[ProcessingRegimeExtract] = Field(default_factory=list)
    measurements: list[MeasurementExtract] = Field(default_factory=list)
    equipment_mentions: list[str] = Field(default_factory=list)
    lab_mentions: list[str] = Field(default_factory=list)
    claims: list[ClaimFinding] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.material_mentions
            or self.processing
            or self.measurements
            or self.equipment_mentions
            or self.lab_mentions
            or self.claims
        )


@dataclass
class ExtractionResult:
    """Extractor output + a transparent repair/retry trace (§6.9)."""

    extract: FullExperimentExtract
    attempts: int = 1
    repaired: bool = False
    dropped: int = 0
    dropped_reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dropped_all: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "extract": self.extract.model_dump(),
            "counts": {
                "material_mentions": len(self.extract.material_mentions),
                "processing": len(self.extract.processing),
                "measurements": len(self.extract.measurements),
                "equipment_mentions": len(self.extract.equipment_mentions),
                "lab_mentions": len(self.extract.lab_mentions),
                "claims": len(self.extract.claims),
                "findings": sum(1 for c in self.extract.claims if c.claim_type == "finding"),
                "assertions": sum(1 for c in self.extract.claims if c.claim_type == "claim"),
            },
            "repair": {
                "attempts": self.attempts,
                "repaired": self.repaired,
                "dropped": self.dropped,
                "dropped_reasons": self.dropped_reasons,
                "errors": self.errors,
                "dropped_all": self.dropped_all,
            },
        }


class _SupportsComplete(Protocol):
    def complete(
        self,
        user: str,
        *,
        system: str | None = ...,
        model: str | None = ...,
        max_tokens: int = ...,
    ) -> str: ...


# --------------------------------------------------------------------------- #
# Prompt                                                                       #
# --------------------------------------------------------------------------- #
SYSTEM = (
    "Ты — экстрактор описаний экспериментов для горно-металлургической R&D базы. "
    "Из фрагмента текста извлеки ОДИН описанный эксперимент: материалы, режимы "
    "обработки, измерения, оборудование, лаборатории и утверждения. Извлекай ТОЛЬКО "
    "факты, дословно подтверждённые фрагментом; evidence_text обязан быть точной "
    "подстрокой текста. Ничего не выдумывай. Отвечай ТОЛЬКО валидным JSON."
)

_SCHEMA_HINT = (
    '{"title":str|null,'
    '"material_mentions":[str],'
    '"processing":[{"operation":str,"temperature_c":number|null,"time_h":number|null,'
    '"atmosphere":str|null,"evidence_text":str,"confidence":0..1}],'
    '"measurements":[{"material":str|null,"property":str,"value":number|null,'
    '"unit":str|null,"condition":str|null,"effect_direction":'
    '"increase|decrease|no_change"|null,"evidence_text":str,"confidence":0..1}],'
    '"equipment_mentions":[str],'
    '"lab_mentions":[str],'
    '"claims":[{"statement":str,"claim_type":"claim|finding",'
    '"about_material":str|null,"about_property":str|null,"about_regime":str|null,'
    '"evidence_text":str,"confidence":0..1}]}'
)

_INSTRUCTION = (
    "Верни JSON строго по схеме (не добавляй других ключей):\n" + _SCHEMA_HINT + "\n"
    "claim_type: 'finding' — эмпирический наблюдённый/измеренный результат; "
    "'claim' — общее утверждение, гипотеза или рекомендация. "
    "about_material/about_property/about_regime — поверхностные упоминания, к которым "
    "относится утверждение (иначе null). evidence_text — дословная цитата из фрагмента.\n\n"
    "ФРАГМЕНТ:\n"
)


def _build_user(text: str) -> str:
    return _INSTRUCTION + text[:_MAX_PROMPT_CHARS]


def _repair_user(base_user: str, error: str) -> str:
    return (
        base_user
        + "\n\nПРЕДЫДУЩИЙ ОТВЕТ БЫЛ НЕВАЛИДНЫМ:\n"
        + error[:500]
        + "\nИсправь и верни ТОЛЬКО корректный JSON строго по схеме выше."
    )


# --------------------------------------------------------------------------- #
# Claim vs Finding derivation (§8.1) — deterministic cross-check              #
# --------------------------------------------------------------------------- #
def derive_claim_type(statement: str) -> tuple[ClaimType, FineClass, tuple[str, ...]]:
    """Deterministically split a statement into claim vs finding (§8.1).

    Reuses the rule cue-word classifier for the finer 4-way label, then folds it to
    the coarse claim|finding axis: an empirical *finding* (or a numeric comparison)
    reads as ``finding``; recommendation/limitation/qualitative comparison read as
    ``claim``.
    """
    cc = classify_claim(statement)
    fine: FineClass = cc.claim_type  # type: ignore[assignment]
    if fine == "finding":
        coarse: ClaimType = "finding"
    elif fine == "comparison" and _NUM.search(statement):
        coarse = "finding"  # a numeric comparison is an observed result
    else:
        coarse = "claim"
    return coarse, fine, cc.cues


# --------------------------------------------------------------------------- #
# Cleaning: drop no-span facts + normalise claim_type before strict validation #
# --------------------------------------------------------------------------- #
def _has_span(row: Any) -> bool:
    return isinstance(row, dict) and bool(str(row.get("evidence_text", "") or "").strip())


def _clean(data: dict[str, Any]) -> tuple[dict[str, Any], int, list[str]]:
    """Drop facts without an evidence span and pre-normalise claim rows.

    Returns the cleaned payload, the number of dropped facts and their reasons.
    Runs BEFORE strict Pydantic validation so an empty ``evidence_text`` is a
    silent drop (not a repair-triggering error), while a genuinely malformed value
    (e.g. ``confidence=1.5``) still surfaces as a ``ValidationError`` → repair.
    """
    dropped = 0
    reasons: list[str] = []
    out: dict[str, Any] = {"title": data.get("title")}

    for key in ("material_mentions", "equipment_mentions", "lab_mentions"):
        vals = data.get(key) or []
        out[key] = [str(v).strip() for v in vals if isinstance(v, str) and str(v).strip()]

    for key in ("processing", "measurements"):
        kept = []
        for row in data.get(key) or []:
            if _has_span(row):
                kept.append(row)
            else:
                dropped += 1
                reasons.append(f"{key}: empty evidence_text")
        out[key] = kept

    claims = []
    for row in data.get("claims") or []:
        if not isinstance(row, dict):
            dropped += 1
            reasons.append("claims: not an object")
            continue
        statement = str(row.get("statement") or row.get("text") or "").strip()
        row.setdefault("statement", statement)
        # A claim's evidence may fall back to its own statement text.
        if not str(row.get("evidence_text", "") or "").strip():
            row["evidence_text"] = statement
        if not statement or not str(row.get("evidence_text", "")).strip():
            dropped += 1
            reasons.append("claims: empty statement/evidence_text")
            continue
        # Derive/repair the claim|finding label and attach the rule cross-check.
        coarse, fine, _cues = derive_claim_type(statement)
        model_label = row.get("claim_type")
        if model_label not in ("claim", "finding"):
            row["claim_type"] = coarse
            row["rule_agrees"] = None
        else:
            row["rule_agrees"] = model_label == coarse
        row["fine_class"] = fine
        claims.append(row)
    out["claims"] = claims

    return out, dropped, reasons


def _empty() -> FullExperimentExtract:
    return FullExperimentExtract()


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #
def extract_experiment(
    text: str,
    *,
    model: str | None = None,
    llm: _SupportsComplete | None = None,
    max_repairs: int = 2,
    max_tokens: int = 1800,
) -> ExtractionResult:
    """Extract one ``FullExperimentExtract`` from *text* with retry/repair (§6.9).

    On invalid JSON or a Pydantic ``ValidationError`` the model is re-prompted with
    the concrete error (up to ``max_repairs`` extra calls). If the budget is
    exhausted the result is an empty extract with ``dropped_all=True`` — a
    controlled drop, never an exception.
    """
    if not text or len(text.strip()) < _MIN_CHARS:
        return ExtractionResult(_empty(), attempts=0)

    client = llm or get_llm()
    base_user = _build_user(text)
    errors: list[str] = []
    err_note = ""

    for attempt in range(max_repairs + 1):
        user = base_user if not err_note else _repair_user(base_user, err_note)
        try:
            raw = client.complete(user, system=SYSTEM, model=model, max_tokens=max_tokens)
        except Exception as exc:  # network/provider error — bounded retry.
            err_note = f"LLM call failed: {type(exc).__name__}: {exc}"
            errors.append(err_note)
            _log.warning("experiment_extract.llm_error", attempt=attempt, error=str(exc)[:160])
            continue

        data = _try_parse_json(raw)
        if not isinstance(data, dict):
            err_note = "Ответ не является валидным JSON-объектом верхнего уровня."
            errors.append(err_note)
            _log.warning("experiment_extract.invalid_json", attempt=attempt, raw=str(raw)[:160])
            continue

        cleaned, dropped, reasons = _clean(data)
        try:
            extract = FullExperimentExtract.model_validate(cleaned)
        except ValidationError as ve:
            err_note = f"Pydantic validation error: {ve}"
            errors.append(err_note[:300])
            _log.warning(
                "experiment_extract.validation_error", attempt=attempt, error=str(ve)[:200]
            )
            continue

        return ExtractionResult(
            extract=extract,
            attempts=attempt + 1,
            repaired=attempt > 0,
            dropped=dropped,
            dropped_reasons=reasons,
            errors=errors,
        )

    # Retry/repair budget exhausted → controlled drop (§6.9).
    _log.warning("experiment_extract.controlled_drop", attempts=max_repairs + 1)
    return ExtractionResult(
        extract=_empty(),
        attempts=max_repairs + 1,
        repaired=True,
        errors=errors,
        dropped_all=True,
    )
