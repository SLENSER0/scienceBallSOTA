"""Governed, offline-safe LLM claim extraction from prose (§25.6).

Prose chunks (running free text — «проза») are the corpus's richest yet least
structured modality. A table row is trivially parsed; a sentence such as
*«микротвёрдость покрытия достигала 320 HV при плотности тока 5 А/дм²»* hides the
same measurement in language. Historically the ingestion node only logged prose
as a *coverage blind spot* (``seen > 0, emitted = 0``, §25.5) and emitted zero
facts, so every measurement stated only in prose was silently lost.

This module turns the previously-inactive ``llm_claims_from_text`` on, but does so
**safely and governed**:

* **Governed** — every extracted datum is returned as a *proposal*
  (``status="proposed"``, ``ProseClaimProposal``), never written to the graph. It
  must flow through the same ``proposal → validate → review`` path as any other
  candidate. This module produces proposals; it never merges them.
* **Evidence reuse** — a prose claim does **not** mint a fresh ``EvidenceSpan``.
  It reuses the *source chunk's* span (``ChunkSpan``): the chunk already anchors a
  ``(doc_id, page, char_start, char_end)`` range, and the claim inherits it. This
  keeps provenance single-sourced (§25.6, «переиспользовать EvidenceSpan исходного
  чанка»).
* **Offline-safe** — when the LLM is unavailable *or* the ``llm_prose_claims``
  feature flag is off, no facts are emitted. Instead the chunk is recorded as a
  coverage blind spot (``seen = 1, emitted = 0``) and the modality is stamped with
  a **high ``p_missed``** via the static prose recall prior (§25.10 ``PROSE_OFFLINE``
  → recall 0.15 → ``p_missed`` 0.85), so the absence layer treats prose gaps as
  probable extraction misses rather than genuine real-world absences.

The deterministic :func:`kg_extractors.property_extractor.extract_properties` pass
always runs (LLM-independent): it does *not* emit facts, but it tells us the chunk
*discusses* controlled properties — the honest denominator behind the coverage
``seen`` count and a stronger ``p_missed`` signal for a prose chunk that clearly
talks about a property yet yielded no governed claim.

Pure and side-effect-free: no graph writes, no store reads. The LLM client is
injected (or lazily constructed via :func:`kg_extractors.llm.get_llm`) so the whole
path is unit-testable with a stub and the offline branch needs no network at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from kg_common import get_logger, get_settings
from kg_extractors.property_extractor import extract_properties

_log = get_logger("prose_claims")

# Feature-flag attribute name on Settings (§25.6). Read defensively via getattr so
# this module works whether or not the flag has been added to config.Settings yet
# (the flag patch is described in the router/wiring, not applied here).
FLAG_ATTR = "llm_prose_claims_enabled"

# Prose modality key used for the recall-prior lookup (§25.10).
PROSE_MODALITY = "prose"

# Cap on characters sent to the LLM per chunk — a prose chunk is already small,
# but this bounds a pathological giant paragraph.
_MAX_PROMPT_CHARS = 6000

_SYSTEM = (
    "Ты — точный экстрактор измерений из научного текста по горному делу, "
    "металлургии и материаловедению. Извлекай ТОЛЬКО явно указанные в тексте "
    "числовые измерения свойств материалов. Никогда ничего не додумывай. "
    "Если измерений нет — верни пустой список."
)

_INSTRUCTION = (
    "Из текста ниже извлеки измерения в формате JSON — объект с ключом "
    '"claims": список объектов {"material": str, "property": str, "value": number, '
    '"unit": str|null, "qualifier": str|null}. '
    'Поле "material" — материал/сплав/покрытие, к которому относится измерение '
    '(если явно назван, иначе null). "property" — измеряемое свойство. '
    '"value" — число. "unit" — единица измерения как в тексте. '
    '"qualifier" — краткое условие/режим, если указано (иначе null). '
    "Бери только то, что дословно присутствует в тексте.\n\nТЕКСТ:\n"
)


class _LLMLike(Protocol):
    """Minimal LLM surface used here — satisfied by :class:`kg_extractors.llm.LLMClient`."""

    def complete_json(self, user: str, *, system: str | None = ..., **kw: Any) -> Any: ...


@dataclass(frozen=True)
class ChunkSpan:
    """The source prose chunk's evidence span — reused by every claim it yields.

    ``chunk_id`` / ``doc_id`` identify the chunk; ``page`` and the half-open
    ``[char_start, char_end)`` range locate it in the document. A prose claim never
    mints its own span — it points back here (§25.6).
    """

    chunk_id: str
    doc_id: str
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass(frozen=True)
class ProseClaimProposal:
    """One governed measurement proposal extracted from prose (§25.6).

    ``status`` is always ``"proposed"`` — the claim is a *candidate* that must pass
    ``validate → review`` before it can become an Observation. ``evidence`` is the
    reused source-chunk span (no new EvidenceSpan). ``value`` may be ``None`` when
    the model surfaced a property mention without a parseable number.
    """

    material: str | None
    property: str
    value: float | None
    unit: str | None
    qualifier: str | None
    evidence: ChunkSpan
    status: str = "proposed"
    source: str = "llm_claims_from_text"

    def as_dict(self) -> dict:
        return {
            "material": self.material,
            "property": self.property,
            "value": self.value,
            "unit": self.unit,
            "qualifier": self.qualifier,
            "evidence": self.evidence.as_dict(),
            "status": self.status,
            "source": self.source,
        }


@dataclass(frozen=True)
class CoverageRecord:
    """Best-effort coverage telemetry for one prose chunk (§25.5 / §25.6).

    ``seen`` is 1 (the chunk was processed); ``emitted`` is the number of governed
    proposals produced (0 when offline/disabled). ``property_mentions`` is the
    deterministic count of controlled properties discussed in the chunk — the honest
    denominator that makes an ``emitted == 0`` prose chunk a credible blind spot.
    """

    modality: str
    seen: int
    emitted: int
    property_mentions: int

    def as_dict(self) -> dict:
        return {
            "modality": self.modality,
            "seen": self.seen,
            "emitted": self.emitted,
            "property_mentions": self.property_mentions,
        }


@dataclass(frozen=True)
class ProseExtraction:
    """Result of :func:`llm_claims_from_text` for one prose chunk (§25.6).

    ``proposals`` are governed candidates (never merged). ``coverage`` is the
    seen/emitted telemetry. ``offline`` is ``True`` when no LLM ran (flag off or no
    client) — then ``proposals`` is empty and ``p_missed`` is the high offline prose
    prior. ``p_missed`` = ``1 - recall`` from the static modality prior (§25.10).
    """

    proposals: list[ProseClaimProposal]
    coverage: CoverageRecord
    offline: bool
    p_missed: float
    reason: str
    property_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "proposals": [p.as_dict() for p in self.proposals],
            "coverage": self.coverage.as_dict(),
            "offline": self.offline,
            "p_missed": self.p_missed,
            "reason": self.reason,
            "property_ids": list(self.property_ids),
        }


def _flag_enabled(explicit: bool | None) -> bool:
    """Resolve the feature flag: explicit override wins, else Settings, else False."""
    if explicit is not None:
        return explicit
    try:
        return bool(getattr(get_settings(), FLAG_ATTR, False))
    except Exception:  # pragma: no cover - settings must never break extraction
        return False


def _has_llm_key() -> bool:
    """True when an OpenRouter key is configured (LLM calls can succeed)."""
    try:
        return bool(get_settings().llm_api_key.get_secret_value())
    except Exception:  # pragma: no cover
        return False


def _prose_p_missed(*, llm_enabled: bool) -> float:
    """High-when-offline ``p_missed`` for prose via the static recall prior (§25.10)."""
    # Imported lazily so kg_extractors does not hard-depend on kg_retrievers at import.
    from kg_retrievers.modality_recall_prior import recall_for_context

    prior = recall_for_context(PROSE_MODALITY, llm_enabled=llm_enabled)
    return round(max(0.0, min(1.0, 1.0 - prior.recall)), 4)


def _coerce_value(raw: Any) -> float | None:
    """Best-effort float coercion; ``None`` when the model gave no clean number."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        cleaned = raw.strip().replace(",", ".").replace(" ", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _blind_spot(
    *, property_ids: list[str], n_mentions: int, reason: str
) -> ProseExtraction:
    """Offline/disabled outcome: zero facts, honest coverage, high ``p_missed`` (§25.6)."""
    return ProseExtraction(
        proposals=[],
        coverage=CoverageRecord(
            PROSE_MODALITY, seen=1, emitted=0, property_mentions=n_mentions
        ),
        offline=True,
        p_missed=_prose_p_missed(llm_enabled=False),
        reason=reason,
        property_ids=property_ids,
    )


def _parse_claims(payload: Any) -> list[dict]:
    """Normalise the LLM payload into a list of claim dicts (tolerant of shapes)."""
    if isinstance(payload, dict):
        payload = payload.get("claims", [])
    if not isinstance(payload, list):
        return []
    out: list[dict] = []
    for item in payload:
        if isinstance(item, dict) and item.get("property"):
            out.append(item)
    return out


def llm_claims_from_text(
    text: str,
    *,
    chunk_id: str,
    doc_id: str,
    page: int | None = None,
    char_start: int | None = None,
    char_end: int | None = None,
    enabled: bool | None = None,
    llm: _LLMLike | None = None,
    model: str | None = None,
) -> ProseExtraction:
    """Extract governed measurement proposals from a prose chunk (§25.6).

    Always runs the deterministic property-mention pass to size the coverage
    denominator. Then, **only when** the ``llm_prose_claims`` flag is on *and* an LLM
    is available, it asks the model for explicit measurements and returns each as a
    ``ProseClaimProposal`` whose evidence is the *reused* source-chunk span. When the
    flag is off, no LLM client is supplied, or the call fails, it emits **zero** facts
    and records the chunk as a high-``p_missed`` coverage blind spot (``seen=1,
    emitted=0``) — the honest offline behaviour (§25.5 / §25.10).

    ``enabled`` overrides the config flag (used by feature-flag tests). ``llm`` injects
    a client (defaults to :func:`kg_extractors.llm.get_llm`). The function never writes
    to a store and never merges a proposal — governance happens downstream.
    """
    span = ChunkSpan(
        chunk_id=chunk_id,
        doc_id=doc_id,
        page=page,
        char_start=char_start,
        char_end=char_end,
    )
    mentions = extract_properties(text or "")
    property_ids = sorted({m.property_id for m in mentions})
    flag_on = _flag_enabled(enabled)

    # --- Offline / disabled branch: honest blind spot, high p_missed. ------------
    if not flag_on:
        return _blind_spot(
            property_ids=property_ids,
            n_mentions=len(mentions),
            reason="feature flag llm_prose_claims disabled",
        )

    client = llm
    if client is None:
        if not _has_llm_key():
            return _blind_spot(
                property_ids=property_ids,
                n_mentions=len(mentions),
                reason="no LLM API key configured",
            )
        from kg_extractors.llm import get_llm

        client = get_llm()

    # --- LLM branch: governed proposals with reused chunk evidence. --------------
    try:
        payload = client.complete_json(
            _INSTRUCTION + (text or "")[:_MAX_PROMPT_CHARS],
            system=_SYSTEM,
            model=model,
        )
    except Exception as exc:  # network / model / JSON — degrade to blind spot.
        _log.warning("prose_claims.llm_failed", chunk_id=chunk_id, error=str(exc)[:200])
        return _blind_spot(
            property_ids=property_ids,
            n_mentions=len(mentions),
            reason=f"LLM extraction failed: {type(exc).__name__}",
        )

    proposals: list[ProseClaimProposal] = []
    for claim in _parse_claims(payload):
        material = claim.get("material")
        proposals.append(
            ProseClaimProposal(
                material=str(material) if material else None,
                property=str(claim["property"]),
                value=_coerce_value(claim.get("value")),
                unit=(str(claim["unit"]) if claim.get("unit") else None),
                qualifier=(str(claim["qualifier"]) if claim.get("qualifier") else None),
                evidence=span,  # reuse the source chunk's span — no new EvidenceSpan.
            )
        )

    _log.info(
        "prose_claims.extracted",
        chunk_id=chunk_id,
        emitted=len(proposals),
        property_mentions=len(mentions),
    )
    return ProseExtraction(
        proposals=proposals,
        coverage=CoverageRecord(
            PROSE_MODALITY, seen=1, emitted=len(proposals), property_mentions=len(mentions)
        ),
        offline=False,
        p_missed=_prose_p_missed(llm_enabled=True),
        reason="ok" if proposals else "LLM returned no measurements",
        property_ids=property_ids,
    )


def proposals_to_json(extraction: ProseExtraction) -> str:
    """Serialise an extraction to a compact JSON string (transport helper)."""
    return json.dumps(extraction.as_dict(), ensure_ascii=False)
