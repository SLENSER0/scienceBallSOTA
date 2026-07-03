"""§7.5 Node 3 — решение об уточнении сущности / entity-resolution clarify gate.

The graph-agent's resolution node maps a mention to one or more canonical
entities, each with a ``confidence`` score. This module decides two orthogonal
things, purely from the candidate list — no store access:

* **should_clarify** — задать вопрос пользователю only when ambiguity actually
  *blocks the answer*: the request is ``critical`` **and** the top two
  candidates are near-ties (top-two confidence gap ``< margin``). A clear winner
  never triggers a clarification, and a non-critical mention is left to
  best-effort resolution even when ambiguous.
* **should_review** — flag for human review when even the best candidate is weak
  (top ``confidence < low_conf``), tagging ``gap_type`` with the fixed reason
  ``'low_confidence_entity_resolution'``.

Deterministic and dependency-free. The candidate dicts are sorted by
``confidence`` descending internally, so callers may pass them in any order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Fixed §7.5 review reason for a weakly-resolved entity (низкая уверенность).
_GAP_LOW_CONF = "low_confidence_entity_resolution"


@dataclass(frozen=True)
class ClarifyDecision:
    """Outcome of the §7.5 Node 3 clarify/review gate over resolution candidates.

    ``should_clarify`` is ``True`` only when a clarification is worth asking —
    ambiguity that blocks the answer. ``should_review`` is ``True`` when the best
    candidate is too weak to trust, in which case ``gap_type`` names the reason
    (иначе ``None``). ``best_candidate`` is the highest-confidence candidate, or
    ``None`` for an empty candidate list.
    """

    should_clarify: bool
    should_review: bool
    gap_type: str | None
    best_candidate: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{should_clarify, should_review, gap_type, best_candidate}``."""
        return {
            "should_clarify": self.should_clarify,
            "should_review": self.should_review,
            "gap_type": self.gap_type,
            "best_candidate": self.best_candidate,
        }


def decide_resolution(
    candidates: list[dict[str, Any]],
    critical: bool,
    margin: float = 0.1,
    low_conf: float = 0.5,
) -> ClarifyDecision:
    """Decide whether to clarify and/or review an entity resolution (§7.5 Node 3).

    Each candidate is a dict with ``canonical_id`` and ``confidence``; the list is
    sorted by ``confidence`` descending internally, so input order is irrelevant.

    ``should_clarify`` is ``True`` **iff** ``critical`` is set *and* the gap
    between the top two confidences is ``< margin`` — an ambiguity that blocks the
    answer (неоднозначность, мешающая ответу). A clear winner or a non-critical
    mention yields ``False``. With fewer than two candidates there is nothing to
    disambiguate, so clarification is never requested.

    ``should_review`` is ``True`` when the top confidence is ``< low_conf``, and
    ``gap_type`` is then set to ``'low_confidence_entity_resolution'`` (иначе
    ``None``). ``best_candidate`` is the highest-confidence entry, ``None`` when
    ``candidates`` is empty.
    """
    ranked = sorted(candidates, key=lambda c: c["confidence"], reverse=True)
    if not ranked:
        return ClarifyDecision(
            should_clarify=False,
            should_review=False,
            gap_type=None,
            best_candidate=None,
        )

    best = ranked[0]
    top_conf = best["confidence"]

    ambiguous = len(ranked) >= 2 and (top_conf - ranked[1]["confidence"]) < margin
    should_clarify = bool(critical and ambiguous)

    should_review = top_conf < low_conf
    gap_type = _GAP_LOW_CONF if should_review else None

    return ClarifyDecision(
        should_clarify=should_clarify,
        should_review=should_review,
        gap_type=gap_type,
        best_candidate=best,
    )
