"""Cross-domain technology transfer recommendations (§24.12).

Recommends technologies (candidates) drawn from *adjacent* domains — never the
query's own domain — and explains each pick with the §24.12 *reason taxonomy*:
``composition_similarity``, ``process_condition_match``, ``equipment_available``,
``geography_analogy`` and ``prior_lab_experience``. This is deliberately distinct
from ``similar_cases`` (same-pool composition/process/geography ranking): here the
value is *transfer* across a domain boundary, so a candidate sharing the query's
domain carries no cross-domain signal and is excluded outright.

Рекомендует технологии из смежных областей (не из области запроса) и объясняет
каждую рекомендацию таксономией причин §24.12. В отличие от ``similar_cases``,
кандидаты из той же области исключаются — переноса между областями там нет.

Reason firing (per candidate, canonical order preserved):
- ``composition_similarity`` — query/candidate ``elements`` share a non-empty set;
- ``process_condition_match`` — ``process`` present and exactly equal;
- ``equipment_available`` — ``equipment`` present and exactly equal;
- ``geography_analogy`` — ``geography`` present and exactly equal;
- ``prior_lab_experience`` — candidate ``lab_id`` is in query ``known_labs``.

Score is the sum of fired reason weights (``REASON_WEIGHTS``). Results sort by
score descending, then ``candidate_id`` ascending. Pure, read-only data logic —
no store access.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# §24.12 reason taxonomy weights. composition_similarity is strongest; the five
# weights sum to exactly 1.0 (see ``test_reason_weights_sum_to_one``).
REASON_WEIGHTS: dict[str, float] = {
    "composition_similarity": 0.30,
    "process_condition_match": 0.20,
    "equipment_available": 0.20,
    "geography_analogy": 0.15,
    "prior_lab_experience": 0.15,
}

# Canonical reason order used for both firing and the emitted ``reasons`` tuple.
_REASON_ORDER: tuple[str, ...] = tuple(REASON_WEIGHTS)


@dataclass(frozen=True)
class TransferRecommendation:
    """One cross-domain transfer recommendation (§24.12).

    - ``candidate_id`` — id of the recommended (adjacent-domain) technology;
    - ``score`` — sum of fired reason weights in ``[0, 1]``;
    - ``reasons`` — fired reason names in canonical taxonomy order.
    """

    candidate_id: str
    score: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping; ``reasons`` round-trips as a list."""
        return {
            "candidate_id": self.candidate_id,
            "score": self.score,
            "reasons": list(self.reasons),
        }


def _as_set(value: object) -> set[object]:
    """Coerce an ``elements`` field into a set (empty for ``None``/scalars)."""
    if value is None:
        return set()
    if isinstance(value, (str, bytes)):
        return {value}
    if isinstance(value, Iterable):
        return set(value)
    return {value}


def _exact_match(query: dict, candidate: dict, field: str) -> bool:
    """True when ``field`` is present (non-``None``) on both and equal."""
    q = query.get(field)
    c = candidate.get(field)
    return q is not None and q == c


def _fired_reasons(query: dict, candidate: dict) -> tuple[str, ...]:
    """Return the fired reason names for ``candidate`` in canonical order."""
    fired: list[str] = []
    if _as_set(query.get("elements")) & _as_set(candidate.get("elements")):
        fired.append("composition_similarity")
    if _exact_match(query, candidate, "process"):
        fired.append("process_condition_match")
    if _exact_match(query, candidate, "equipment"):
        fired.append("equipment_available")
    if _exact_match(query, candidate, "geography"):
        fired.append("geography_analogy")
    known_labs = _as_set(query.get("known_labs"))
    if candidate.get("lab_id") is not None and candidate.get("lab_id") in known_labs:
        fired.append("prior_lab_experience")
    # Preserve canonical order regardless of insertion order above.
    return tuple(r for r in _REASON_ORDER if r in fired)


def recommend_transfers(
    query: dict,
    candidates: Sequence[dict],
    min_score: float = 0.0,
) -> tuple[TransferRecommendation, ...]:
    """Recommend adjacent-domain transfers for ``query`` (§24.12).

    Candidates sharing the query ``domain`` are excluded (no cross-domain
    signal). For each remaining candidate, reasons fire per the §24.12 taxonomy
    and the score is the sum of their ``REASON_WEIGHTS``. Recommendations with a
    score ``< min_score`` are dropped. The result is sorted by score descending,
    then ``candidate_id`` ascending.
    """
    query_domain = query.get("domain")
    recs: list[TransferRecommendation] = []
    for candidate in candidates:
        if candidate.get("domain") == query_domain:
            continue
        reasons = _fired_reasons(query, candidate)
        score = sum(REASON_WEIGHTS[r] for r in reasons)
        if score < min_score:
            continue
        recs.append(
            TransferRecommendation(
                candidate_id=str(candidate.get("candidate_id")),
                score=score,
                reasons=reasons,
            )
        )
    recs.sort(key=lambda r: (-r.score, r.candidate_id))
    return tuple(recs)
