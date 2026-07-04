"""§25.13 — honest no-data self-check for the chat surface.

When the agent answers a data-bearing question with «этой темы не изучали», that
claim is only safe when the underlying absence is a *настоящий пробел*. If the
absence layer classifies the same cell as ``possible_miss`` (упомянуто, но не
измерено) or ``abstain`` — or simply assigns a high ``p_extractor_missed`` — the
honest statement is not «данных нет» but «возможно, факт есть, но извлечение его
пропустило». This router lets the chat UI ask exactly that question of an
answer's gaps *after* the fact, without re-running the agent and without touching
the graph.

It writes **no** new absence math: every gap is folded through the already-built
§25.11/§25.13 modules —

* :func:`kg_retrievers.absence_signals.classify_cell` re-derives the verdict and
  the two Bayesian posteriors for any gap that names a (material, property) cell;
* :func:`kg_retrievers.absence_self_check.summarize_absence` rolls the annotated
  batch into per-verdict counts, a high-miss-risk count, a ``calibrated`` flag and
  ready-to-show RU/EN warnings;
* :func:`kg_retrievers.absence_self_check.should_flag_hypothesis` decides, per
  gap, whether it may be presented as unstudied at all (``possible_miss`` /
  ``abstain`` must be held back).

Strictly **read-only**. Gaps that already carry ``absence_verdict`` /
``p_extractor_missed`` (e.g. produced by the agent or ``/gaps/absence``) are
honoured as-is; only gaps that name a resolvable cell are re-classified live. A
distinct ``/chat/absence-self-check`` path under the existing ``/chat`` prefix; no
collision with :mod:`api_gateway.routers.chat`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_user

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# RU/EN verdict labels — the chat banner and per-gap chips render these. Kept
# server-side so the endpoint is self-describing (§25.13/§25.14 vocabulary).
_VERDICT_LABELS: dict[str, dict[str, str]] = {
    "genuine_gap": {"ru": "реальный пробел", "en": "genuine gap"},
    "possible_miss": {"ru": "возможно пропуск извлечения", "en": "possible extraction miss"},
    "retracted": {"ru": "ретрагировано", "en": "retracted"},
    "abstain": {"ru": "неопределённо", "en": "undecided"},
    "present": {"ru": "покрыто", "en": "present"},
    "covered": {"ru": "покрыто (без значения)", "en": "covered (no value)"},
    "unknown": {"ru": "не классифицировано", "en": "unclassified"},
}

# Candidate keys under which a gap may name its material / property cell. Chat
# gaps come from several producers, so accept the common spellings.
_MATERIAL_KEYS = ("material_id", "materialId", "subject_id", "subjectId", "entity_id")
_PROPERTY_KEYS = ("property_name", "propertyName", "property_id", "propertyId", "property")


class AbsenceSelfCheckBody(BaseModel):
    """POST body — the answer's gaps plus the high-miss threshold (§25.13)."""

    gaps: list[dict[str, Any]] = Field(default_factory=list)
    # Inclusive P(extractor missed) at which a gap counts as high-risk in the
    # summary and forces the «риск пропуска» banner. Matches summarize_absence.
    high_miss_at: float = Field(default=0.6, ge=0.0, le=1.0)


def _cell_ref(gap: dict) -> tuple[str, str] | None:
    """Return the ``(material_id, property)`` a gap names, or ``None``.

    Accepts the several spellings chat gaps use; also digs one level into an
    ``about`` list (``[{id, name}, ...]``) for the material id when no flat key is
    present. Returns ``None`` when either coordinate is missing — such a gap keeps
    whatever absence fields it already carries and is not re-classified.
    """
    material = next((str(gap[k]) for k in _MATERIAL_KEYS if gap.get(k)), None)
    if material is None:
        about = gap.get("about")
        if isinstance(about, list) and about and isinstance(about[0], dict):
            mid = about[0].get("id")
            material = str(mid) if mid else None
    prop = next((str(gap[k]) for k in _PROPERTY_KEYS if gap.get(k)), None)
    if material is None or prop is None:
        return None
    return material, prop


def _annotate_one(store: Any, gap: dict) -> dict[str, Any]:
    """Return ``gap`` enriched with a §25.11 verdict + posteriors (read-only).

    A gap that already carries ``absence_verdict`` is trusted and returned with
    only derived display fields added. A gap that names a resolvable cell is
    classified live via :func:`classify_cell`. Any classification error (missing
    node, offline store) degrades gracefully to an ``unknown`` verdict rather than
    failing the whole batch.
    """
    enriched = dict(gap)

    if not enriched.get("absence_verdict"):
        ref = _cell_ref(gap)
        if ref is not None and store is not None:
            try:
                from kg_retrievers.absence_signals import classify_cell

                sig = classify_cell(store, ref[0], ref[1])
                enriched["absence_verdict"] = sig.verdict
                enriched["p_truly_absent"] = sig.p_truly_absent
                enriched["p_extractor_missed"] = sig.p_extractor_missed
                enriched.setdefault(
                    "absence_meta",
                    # No gold-calibrated recall prior on the live profile → heuristic.
                    {"calibrated": False, "method": "heuristic"},
                )
            except Exception:
                enriched.setdefault("absence_verdict", "unknown")
        else:
            enriched.setdefault("absence_verdict", "unknown")

    verdict = enriched.get("absence_verdict") or "unknown"
    p_missed = float(enriched.get("p_extractor_missed") or 0.0)
    enriched["verdict_labels"] = _VERDICT_LABELS.get(verdict, _VERDICT_LABELS["unknown"])
    enriched["extractor_miss_risk_pct"] = round(p_missed * 100)
    return enriched


def _banner(check: Any, hold_back_n: int) -> dict[str, Any] | None:
    """Build the top-of-answer honesty banner, or ``None`` when nothing to warn.

    Fires whenever the batch holds any hold-back gap (``possible_miss`` /
    ``abstain``) or any high extractor-miss-risk cell — the two conditions under
    which «данных нет» would over-claim. Carries a ``calibrated`` flag so the UI
    can mark the estimate as heuristic.
    """
    risky = check.n_possible_miss + check.n_abstain
    if hold_back_n == 0 and check.n_high_miss_risk == 0 and risky == 0:
        return None
    return {
        "severity": "high" if (check.n_high_miss_risk or check.n_possible_miss) else "info",
        "title_ru": "Осторожно с выводом «данных нет»",
        "title_en": "Be careful before claiming «no data»",
        "message_ru": (
            "Возможно, факт есть, но извлечение его пропустило — "
            f"{hold_back_n} из {check.n_gaps} пробелов нельзя выдавать как «тему не изучали»."
        ),
        "message_en": (
            "The fact may exist but extraction missed it — "
            f"{hold_back_n} of {check.n_gaps} gaps must not be presented as unstudied."
        ),
        "n_hold_back": hold_back_n,
        "n_high_miss_risk": check.n_high_miss_risk,
        "calibrated": check.calibrated,
    }


@router.post("/absence-self-check")
def absence_self_check(
    body: AbsenceSelfCheckBody,
    _user: str = Depends(current_user),
) -> dict[str, Any]:
    """Fold a chat answer's gaps into an honest no-data self-check (§25.13).

    Re-classifies every gap that names a (material, property) cell through the
    §25.11 signals, honours gaps that already carry an ``absence_verdict``, and
    returns:

    * ``self_check`` — the §25.13 batch summary (per-verdict counts, high-miss
      count, ``calibrated`` flag, RU/EN warnings);
    * ``gaps`` — each input gap enriched with its verdict, posteriors, RU/EN
      label, ``extractor_miss_risk_pct`` and a ``hold_back`` flag (True when the
      gap must **not** be presented as unstudied);
    * ``banner`` — a ready-to-render honesty banner, or ``null`` when the answer
      is safe to present as-is.

    Strictly read-only: classifies against the live graph but never mutates it.
    """
    from kg_retrievers.absence_self_check import (
        should_flag_hypothesis,
        summarize_absence,
    )

    try:
        from api_gateway.deps import get_store

        store = get_store()
    except Exception:
        store = None

    annotated = [_annotate_one(store, gap) for gap in body.gaps]
    for gap in annotated:
        # should_flag_hypothesis == may-present-as-unstudied → hold_back is its inverse.
        gap["hold_back"] = not should_flag_hypothesis(gap)

    check = summarize_absence(annotated, high_miss_at=body.high_miss_at)
    hold_back_n = sum(1 for g in annotated if g["hold_back"])

    return {
        "self_check": check.as_dict(),
        "hold_back_count": hold_back_n,
        "verdict_labels": _VERDICT_LABELS,
        "banner": _banner(check, hold_back_n),
        "gaps": annotated,
    }
