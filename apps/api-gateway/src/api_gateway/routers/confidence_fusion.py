"""Confidence-fusion в оркестраторе — boost при согласии, конфликт → review (§6.13).

The §6.13 orchestrator merges facts proposed by up to three independent
extraction *layers* — the rule extractor (правило), the ML/NER model (модель) and
the LLM (языковая модель). Two things must happen when several layers speak about
the *same* fact:

* **boost при согласии** — independent layers that concur reinforce each other, so
  the fused confidence is nudged toward ``1.0`` (agreement boost, §6.13);
* **конфликт значений → review** — when the layers report numbers that diverge
  beyond tolerance the fact is *deterministically* routed to the review queue,
  never silently accepted, and the highest-priority layer (rule ≻ llm ≻ ml) still
  supplies the winning value.

Nothing here re-implements that maths — the three deterministic, unit-tested
core modules already exist and are reused verbatim:

* :func:`kg_extractors.extraction_confidence.combine_layers` — fuse the per-layer
  confidences (weighted-mean / noisy-OR) and apply the agreement boost;
* :func:`kg_extractors.value_reconcile.reconcile_numeric` — pick the winning value
  by layer priority and flag a ``conflict`` when the values diverge;
* :func:`kg_extractors.review_routing.route_extraction` — fold the fused
  confidence + a ``conflicting`` flag into an auto-accept / review / reject verdict
  with a review-queue priority (§6.15).

Two endpoints (server profile, Neo4j :8000):

* ``POST /api/v1/confidence-fusion/fuse`` — deterministic orchestrator surface: a
  batch of facts, each carrying its per-layer ``{confidence, value}``, is fused →
  per-fact ``{fused_confidence, reconciled_value, conflict, review}`` plus a
  human-readable explanation. Pure compute, no graph I/O — this is the endpoint
  that reproduces the §6.13 acceptance scenarios (agree → boosted single fact;
  conflict → review).
* ``GET /api/v1/confidence-fusion/live`` — runs the same fusion over the live
  graph: ``Measurement`` nodes are clustered by ``(property, material, unit)`` (the
  same physical fact re-extracted by different layers/sources), each cluster is
  fused, and the clusters where layers *conflict* surface at the top so a curator
  sees exactly which facts the orchestrator sent to review.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from kg_extractors.extraction_confidence import (
    LAYER_LLM,
    LAYER_ML,
    LAYER_RULE,
    combine_layers,
)
from kg_extractors.review_routing import (
    ACTION_AUTO_ACCEPT,
    ACTION_REJECT,
    ACTION_REVIEW,
    REASON_CONFLICTING,
    route_extraction,
)
from kg_extractors.value_reconcile import reconcile_numeric

router = APIRouter(prefix="/api/v1/confidence-fusion", tags=["confidence-fusion"])

#: Canonical layers, in the priority order used for numeric reconciliation
#: (§6.13: rule facts for numbers win over LLM, LLM over ML).
_LAYER_PRIORITY: tuple[str, ...] = (LAYER_RULE, LAYER_LLM, LAYER_ML)
_LAYERS: tuple[str, ...] = (LAYER_RULE, LAYER_ML, LAYER_LLM)

_LAYER_LABEL_RU: dict[str, str] = {
    LAYER_RULE: "правило",
    LAYER_ML: "ML-модель",
    LAYER_LLM: "LLM",
}

_ACTION_LABEL_RU: dict[str, str] = {
    ACTION_AUTO_ACCEPT: "автопринятие",
    ACTION_REVIEW: "на ревью",
    ACTION_REJECT: "отклонить",
}


# --------------------------------------------------------------------------- IO
class LayerVote(BaseModel):
    """One extraction layer's opinion on a fact (§6.13)."""

    confidence: float = Field(ge=0.0, le=1.0)
    value: float | None = None  # numeric candidate (for reconciliation)


class FactIn(BaseModel):
    """A single fact seen by ≥1 extraction layer, awaiting fusion (§6.13)."""

    id: str | None = None
    label: str | None = None  # property / operation name (человекочитаемо)
    unit: str | None = None
    rule: LayerVote | None = None
    ml: LayerVote | None = None
    llm: LayerVote | None = None
    # extra escalation flags raised upstream (unit gate §7.5, OCR §5, …)
    flags: list[str] = Field(default_factory=list)


class FuseRequest(BaseModel):
    facts: list[FactIn] = Field(default_factory=list)
    # tolerance for treating per-layer numbers as agreeing (rel., §6.13)
    rel_tol: float = Field(default=0.02, ge=0.0, le=1.0)
    auto_accept_at: float = Field(default=0.85, ge=0.0, le=1.0)
    reject_at: float = Field(default=0.2, ge=0.0, le=1.0)


class ReviewOut(BaseModel):
    action: str  # auto_accept | review | reject
    action_ru: str
    priority: float
    reasons: list[str]
    needs_review: bool


class FactOut(BaseModel):
    """The fused verdict for one fact (§6.13)."""

    id: str | None
    label: str | None
    # which layers fired + their raw confidences (для прозрачности)
    sources: list[str]
    layer_confidences: dict[str, float]
    # fusion
    fused_confidence: float
    agreement_boost: bool  # ≥2 layers concurred → confidence lifted
    # value reconciliation
    reconciled_value: float | None
    unit: str | None
    chosen_layer: str | None
    conflict: bool  # layers disagreed on the number → forced review
    spread: float
    # routing
    review: ReviewOut
    explanation: str


class FuseResponse(BaseModel):
    total: int
    auto_accept: int
    review: int
    reject: int
    boosted: int  # facts whose confidence was lifted by layer agreement
    conflicts: int  # facts sent to review because layers disagreed on the value
    facts: list[FactOut]


# --------------------------------------------------------------------- fusion core
@dataclass
class _Vote:
    layer: str
    confidence: float
    value: float | None


def _fuse_one(
    *,
    fact_id: str | None,
    label: str | None,
    unit: str | None,
    votes: list[_Vote],
    extra_flags: list[str],
    rel_tol: float,
    thresholds: dict[str, float],
) -> FactOut:
    """Fuse one fact's layer votes into a §6.13 verdict.

    Confidence is fused (+ agreement boost) by
    :func:`combine_layers`; numeric candidates are reconciled by
    :func:`reconcile_numeric` (conflict → review); the fused confidence plus a
    ``conflicting`` flag are routed by :func:`route_extraction`.
    """
    # De-duplicate to one confidence per layer (max wins if a layer voted twice).
    per_layer: dict[str, float] = {}
    per_layer_value: dict[str, float | None] = {}
    for v in votes:
        if v.layer not in per_layer or v.confidence > per_layer[v.layer]:
            per_layer[v.layer] = v.confidence
            per_layer_value[v.layer] = v.value

    # 1) Confidence fusion + agreement boost (§6.13).
    combined = combine_layers(
        rule=per_layer.get(LAYER_RULE),
        ml=per_layer.get(LAYER_ML),
        llm=per_layer.get(LAYER_LLM),
    )
    confs = list(per_layer.values())
    # An agreement boost fires when ≥2 layers are present and concur (spread within
    # the module's tolerance) — mirror that condition to report it to the UI.
    boost = len(confs) >= 2 and (max(confs) - min(confs)) <= 0.25

    # 2) Numeric reconciliation (§6.13): winner by layer priority, conflict flag.
    candidates: list[tuple[str, float, str | None]] = [
        (layer, val, unit)
        for layer, val in per_layer_value.items()
        if val is not None
    ]
    reconciled_value: float | None = None
    chosen_layer: str | None = None
    conflict = False
    spread = 0.0
    if candidates:
        rec = reconcile_numeric(candidates, rel_tol=rel_tol, layer_priority=_LAYER_PRIORITY)
        reconciled_value = rec.value
        chosen_layer = rec.chosen_layer
        conflict = rec.conflict
        spread = rec.spread

    # 3) Routing: conflict forces review, low confidence rejects, high auto-accepts.
    flags = list(dict.fromkeys([f.strip().lower() for f in extra_flags if f.strip()]))
    if conflict and REASON_CONFLICTING not in flags:
        flags.append(REASON_CONFLICTING)
    item = {
        "confidence": combined.value,
        "unit": unit,
        "value": reconciled_value,
        "flags": flags,
    }
    decision = route_extraction(item, thresholds=thresholds)

    return FactOut(
        id=fact_id,
        label=label,
        sources=[_LAYER_LABEL_RU.get(s, s) for s in combined.sources],
        layer_confidences={k: round(v, 6) for k, v in per_layer.items()},
        fused_confidence=combined.value,
        agreement_boost=bool(boost),
        reconciled_value=reconciled_value,
        unit=unit,
        chosen_layer=chosen_layer,
        conflict=conflict,
        spread=spread,
        review=ReviewOut(
            action=decision.action,
            action_ru=_ACTION_LABEL_RU.get(decision.action, decision.action),
            priority=decision.priority,
            reasons=decision.reasons,
            needs_review=decision.needs_review,
        ),
        explanation=_explain(
            sources=combined.sources,
            fused=combined.value,
            boost=bool(boost),
            conflict=conflict,
            chosen_layer=chosen_layer,
            reconciled_value=reconciled_value,
            unit=unit,
            spread=spread,
            action=decision.action,
        ),
    )


def _explain(
    *,
    sources: list[str],
    fused: float,
    boost: bool,
    conflict: bool,
    chosen_layer: str | None,
    reconciled_value: float | None,
    unit: str | None,
    spread: float,
    action: str,
) -> str:
    """Build the RU one-line rationale shown next to the fused verdict."""
    layers_ru = ", ".join(_LAYER_LABEL_RU.get(s, s) for s in sources) or "нет слоёв"
    parts = [f"Слои: {layers_ru} → уверенность {fused:.2f}"]
    if boost:
        parts.append("бонус за согласие слоёв")
    if conflict:
        val = "—" if reconciled_value is None else _fmt(reconciled_value)
        chosen = _LAYER_LABEL_RU.get(chosen_layer or "", chosen_layer or "—")
        parts.append(
            f"конфликт значений (разброс {_fmt(spread)}{(' ' + unit) if unit else ''}) "
            f"→ на ревью; приоритет отдан слою «{chosen}» = {val}"
        )
    parts.append(f"вердикт: {_ACTION_LABEL_RU.get(action, action)}")
    return "; ".join(parts)


def _fmt(x: float | None) -> str:
    if x is None:
        return "—"
    r = round(float(x), 4)
    return str(int(r) if float(r).is_integer() else r)


def _roll_up(facts: list[FactOut]) -> dict[str, int]:
    out = {
        ACTION_AUTO_ACCEPT: 0,
        ACTION_REVIEW: 0,
        ACTION_REJECT: 0,
        "boosted": 0,
        "conflicts": 0,
    }
    for f in facts:
        out[f.review.action] = out.get(f.review.action, 0) + 1
        if f.agreement_boost:
            out["boosted"] += 1
        if f.conflict:
            out["conflicts"] += 1
    return out


# ------------------------------------------------------------------- endpoint: fuse
@router.post("/fuse", response_model=FuseResponse)
def fuse(req: FuseRequest) -> FuseResponse:
    """Fuse per-layer confidences → one verdict per fact (§6.13), pure compute.

    For each fact the present layers' confidences are fused with an agreement
    boost, the numeric candidates are reconciled (highest-priority layer wins;
    divergence flags a ``conflict``), and the result is routed to
    auto-accept / review / reject. A value conflict deterministically forces
    review — the §6.13 acceptance behaviour.
    """
    thresholds = {"auto_accept_at": req.auto_accept_at, "reject_at": req.reject_at}
    out: list[FactOut] = []
    for i, fact in enumerate(req.facts):
        votes: list[_Vote] = []
        for layer, vote in (
            (LAYER_RULE, fact.rule),
            (LAYER_ML, fact.ml),
            (LAYER_LLM, fact.llm),
        ):
            if vote is not None:
                votes.append(_Vote(layer=layer, confidence=vote.confidence, value=vote.value))
        out.append(
            _fuse_one(
                fact_id=fact.id or f"fact-{i}",
                label=fact.label,
                unit=fact.unit,
                votes=votes,
                extra_flags=fact.flags,
                rel_tol=req.rel_tol,
                thresholds=thresholds,
            )
        )

    roll = _roll_up(out)
    # Conflicts / lowest-confidence first — the shakiest facts head the list.
    out.sort(key=lambda f: (not f.conflict, -f.review.priority))
    return FuseResponse(
        total=len(out),
        auto_accept=roll[ACTION_AUTO_ACCEPT],
        review=roll[ACTION_REVIEW],
        reject=roll[ACTION_REJECT],
        boosted=roll["boosted"],
        conflicts=roll["conflicts"],
        facts=out,
    )


# ------------------------------------------------------------------- endpoint: live
def _classify_layer(name: str | None) -> str:
    """Map an extractor id to a §6.13 layer (rule / ml / llm).

    Best-effort by substring: rule/regex/vocab/parser → rule; gliner/bert/ner/spacy
    → ml; llm/gpt/qwen/llama/schema/ie → llm. Unknown ids default to ``ml``.
    """
    if not name:
        return LAYER_ML
    n = str(name).strip().lower()
    if any(t in n for t in ("rule", "regex", "vocab", "parser", "gost", "compos", "unit")):
        return LAYER_RULE
    if any(t in n for t in ("gliner", "matbert", "matsci", "spacy", "ner", "bert")):
        return LAYER_ML
    if any(t in n for t in ("llm", "gpt", "qwen", "llama", "schema", "ie", "graph", "claim")):
        return LAYER_LLM
    return LAYER_ML


_SCAN_CYPHER = (
    "MATCH (ms:Node) WHERE ms.label='Measurement' AND ms.value_normalized IS NOT NULL "
    "OPTIONAL MATCH (ms)-[:Rel {type:'ABOUT_MATERIAL'}]->(mat:Node) "
    "OPTIONAL MATCH (ms)-[:Rel {type:'SUPPORTED_BY'}]->(ev:Node {label:'Evidence'}) "
    "RETURN ms.id, ms.property_name, ms.value_normalized, ms.normalized_unit, "
    "ms.confidence, ms.extractor, ms.extractor_run_id, ev.extractor, ev.confidence, "
    "mat.name LIMIT $limit"
)


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


@dataclass
class _Member:
    ms_id: str
    layer: str
    confidence: float
    value: float


class LiveCluster(BaseModel):
    """A physical fact re-extracted by ≥2 layers, then fused (§6.13)."""

    property_name: str | None
    material: str | None
    unit: str | None
    n_members: int
    fusion: FactOut


class LiveResponse(BaseModel):
    total_measurements: int
    multi_layer_clusters: int
    conflicts: int
    boosted: int
    clusters: list[LiveCluster]


@router.get("/live", response_model=LiveResponse)
def live(
    limit: int = Query(default=4000, ge=1, le=40000),
    rel_tol: float = Query(default=0.02, ge=0.0, le=1.0),
    only_multi: bool = Query(default=True, description="только факты из ≥2 слоёв"),
) -> LiveResponse:
    """Run §6.13 confidence-fusion over the live graph.

    ``Measurement`` nodes are clustered by ``(property, material, unit)`` — the same
    physical fact re-extracted by different layers/sources — and each cluster is
    fused: agreeing layers lift the confidence, conflicting values are routed to
    review. Conflicts surface first so a curator sees the orchestrator's review
    decisions at a glance.
    """
    store = get_store()
    raw = store.rows(_SCAN_CYPHER, {"limit": int(limit)})

    # Collapse (measurement, evidence) rows to one member per measurement, then
    # cluster measurements by their physical-fact identity.
    seen: set[str] = set()
    clusters: dict[tuple[str, str, str], list[_Member]] = {}
    total = 0
    for rec in raw:
        (ms_id, prop, val, unit, ms_conf, ms_extr, ms_run, ev_extr, ev_conf, mat) = rec
        v = _to_float(val)
        if not ms_id or v is None:
            continue
        mid = str(ms_id)
        if mid in seen:
            continue
        seen.add(mid)
        total += 1
        conf = _to_float(ms_conf)
        if conf is None:
            conf = _to_float(ev_conf)
        conf = 0.6 if conf is None else max(0.0, min(1.0, conf))
        layer = _classify_layer(ms_extr or ms_run or ev_extr)
        key = (
            (str(prop).strip().lower() if prop else ""),
            (str(mat).strip().lower() if mat else ""),
            (str(unit).strip().lower() if unit else ""),
        )
        clusters.setdefault(key, []).append(
            _Member(ms_id=mid, layer=layer, confidence=conf, value=v)
        )

    out: list[LiveCluster] = []
    n_conflict = n_boost = 0
    for (prop, mat, unit), members in clusters.items():
        if only_multi and len(members) < 2:
            continue
        votes = [_Vote(layer=m.layer, confidence=m.confidence, value=m.value) for m in members]
        fused = _fuse_one(
            fact_id=members[0].ms_id,
            label=prop or None,
            unit=unit or None,
            votes=votes,
            extra_flags=[],
            rel_tol=rel_tol,
            thresholds={"auto_accept_at": 0.85, "reject_at": 0.2},
        )
        if fused.conflict:
            n_conflict += 1
        if fused.agreement_boost:
            n_boost += 1
        out.append(
            LiveCluster(
                property_name=prop or None,
                material=mat or None,
                unit=unit or None,
                n_members=len(members),
                fusion=fused,
            )
        )

    # Conflicts first, then highest review priority (shakiest facts on top).
    out.sort(key=lambda c: (not c.fusion.conflict, -c.fusion.review.priority))
    return LiveResponse(
        total_measurements=total,
        multi_layer_clusters=len(out),
        conflicts=n_conflict,
        boosted=n_boost,
        clusters=out,
    )
