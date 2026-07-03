"""Deterministic crosswalk conflict policy (§20.3).

Maps external records (from lab systems such as eLabFTW) to canonical KG
entities using a transparent, reproducible decision policy — no ML at call
time. A direct crosswalk hit (a known ``(system, external_id)`` pair) always
wins; otherwise a match probability is classified against fixed thresholds into
``auto_merge`` / ``review`` / ``separate`` so behaviour is fully deterministic
and hand-checkable in CI (§20.3).

Детерминированная политика кросс-уока: сопоставление внешних записей с
каноническими сущностями графа по фиксированным порогам, без ML во время
вызова.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrosswalkThresholds:
    """Fixed decision boundaries for crosswalk classification (§20.3).

    Пороги решений: ``p >= auto_merge`` — авто-слияние, ``review_low <= p <
    auto_merge`` — ручная проверка, иначе — отдельная сущность.
    """

    auto_merge: float = 0.9
    review_low: float = 0.7

    def as_dict(self) -> dict[str, float]:
        """Serialize thresholds / сериализация порогов."""
        return {"auto_merge": self.auto_merge, "review_low": self.review_low}


@dataclass(frozen=True)
class CrosswalkDecision:
    """Outcome of resolving one external record (§20.3).

    Результат разрешения одной внешней записи: действие, вероятность совпадения,
    канонический идентификатор и статус ручной проверки.
    """

    system: str
    external_id: str
    action: str
    match_probability: float | None
    canonical_id: str
    review_status: str

    def as_dict(self) -> dict[str, object]:
        """Serialize decision / сериализация решения."""
        return {
            "system": self.system,
            "external_id": self.external_id,
            "action": self.action,
            "match_probability": self.match_probability,
            "canonical_id": self.canonical_id,
            "review_status": self.review_status,
        }


def classify_action(p: float, th: CrosswalkThresholds = CrosswalkThresholds()) -> str:
    """Classify a match probability into an action (§20.3).

    Returns ``'auto_merge'`` for ``p >= th.auto_merge``, ``'review'`` for
    ``th.review_low <= p < th.auto_merge``, else ``'separate'``.

    Классификация вероятности совпадения в действие по фиксированным порогам.
    """
    if p >= th.auto_merge:
        return "auto_merge"
    if p >= th.review_low:
        return "review"
    return "separate"


def resolve_or_create(
    system: str,
    external_id: str,
    direct_map: dict[tuple[str, str], str],
    match_probability: float | None,
    candidate_canonical_id: str | None,
    new_id: str,
    th: CrosswalkThresholds = CrosswalkThresholds(),
) -> CrosswalkDecision:
    """Resolve an external record to a canonical entity or mint a new id (§20.3).

    Policy / политика:

    * A direct crosswalk hit (``(system, external_id)`` in ``direct_map``) wins:
      action ``'auto_merge'``, ``canonical_id`` = mapped value,
      ``match_probability`` = ``1.0``, ``review_status`` = ``'resolved'``.
    * Otherwise classify ``match_probability`` (``None`` → ``'separate'``):
      * ``'auto_merge'`` → canonical = ``candidate_canonical_id``,
        ``review_status`` = ``'resolved'``.
      * ``'review'`` → canonical = ``candidate_canonical_id``,
        ``review_status`` = ``'pending'``.
      * ``'separate'`` → canonical = ``new_id``, ``review_status`` =
        ``'resolved'``.
    """
    mapped = direct_map.get((system, external_id))
    if mapped is not None:
        return CrosswalkDecision(
            system=system,
            external_id=external_id,
            action="auto_merge",
            match_probability=1.0,
            canonical_id=mapped,
            review_status="resolved",
        )

    action = "separate" if match_probability is None else classify_action(match_probability, th)

    if action == "review":
        canonical_id = candidate_canonical_id if candidate_canonical_id is not None else new_id
        review_status = "pending"
    elif action == "auto_merge":
        canonical_id = candidate_canonical_id if candidate_canonical_id is not None else new_id
        review_status = "resolved"
    else:  # separate
        canonical_id = new_id
        review_status = "resolved"

    return CrosswalkDecision(
        system=system,
        external_id=external_id,
        action=action,
        match_probability=match_probability,
        canonical_id=canonical_id,
        review_status=review_status,
    )
