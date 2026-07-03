"""Similar-case ranking by weighted feature overlap (§24.12).

Ranks stored cases against a query by a weighted blend of overlap across three
dimensions — ``composition`` (shared chemical elements), ``process`` (exact
match) and ``geography`` (exact match) — with equal weights of ``1/3`` each.
Each contributing dimension yields a human-readable reason so the ranking is
explainable. Pure in-memory computation over plain dicts: it does not touch the
Kuzu store (custom node props are not queryable columns anyway; callers
materialise the case dicts via ``get_node`` beforehand).

Ранжирование похожих кейсов по взвешенному перекрытию признаков composition,
process, geography с понятными причинами совпадения (§24.12).
"""

from __future__ import annotations

from dataclasses import dataclass

# Equal weight per dimension: composition, process, geography.
_WEIGHT = 1.0 / 3.0


@dataclass(frozen=True)
class CaseSimilarity:
    """Similarity of one case to the query with contributing reasons (§24.12).

    - ``case_id`` — identifier of the compared case;
    - ``score`` — weighted overlap in ``[0, 1]`` (``1.0`` for an identical case,
      ``0.0`` for a fully disjoint one);
    - ``reasons`` — dimensions that contributed, any of ``composition_match``,
      ``process_match``, ``geography_match`` (empty when nothing overlapped).
    """

    case_id: str
    score: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "score": self.score,
            "reasons": list(self.reasons),
        }


def _composition_overlap(query: dict[str, float], case: dict[str, float]) -> float:
    """Fraction of shared elements as Jaccard of composition key sets (§24.12).

    Elements are compared by presence (keys), not by their numeric fractions:
    ``|shared| / |union|``. Identical key sets → ``1.0``; disjoint → ``0.0``;
    both empty → ``0.0`` (empty union rewards no shared structure).
    """
    q_keys = set(query or {})
    c_keys = set(case or {})
    union = q_keys | c_keys
    if not union:
        return 0.0
    return len(q_keys & c_keys) / len(union)


def _score_case(query: dict, case: dict) -> tuple[float, tuple[str, ...]]:
    """Weighted overlap and reasons for a single case against the query (§24.12)."""
    reasons: list[str] = []
    score = 0.0

    comp = _composition_overlap(query.get("composition", {}), case.get("composition", {}))
    if comp > 0.0:
        score += _WEIGHT * comp
        reasons.append("composition_match")

    if query.get("process") == case.get("process") and query.get("process") is not None:
        score += _WEIGHT
        reasons.append("process_match")

    if query.get("geography") == case.get("geography") and query.get("geography") is not None:
        score += _WEIGHT
        reasons.append("geography_match")

    return score, tuple(reasons)


def rank_similar(
    query: dict,
    cases: list[dict],
    *,
    top: int | None = None,
) -> list[CaseSimilarity]:
    """Rank ``cases`` against ``query`` by weighted feature overlap (§24.12).

    ``query`` and each case carry ``composition: dict[str, float]``,
    ``process: str`` and ``geography: str``. Score blends composition overlap
    (fraction of shared elements), process exact-match and geography exact-match
    with equal ``1/3`` weights. Results are sorted by descending score then
    ascending ``case_id``; ``top`` caps the number returned. Empty ``cases`` →
    empty list.
    """
    results: list[CaseSimilarity] = []
    for case in cases:
        score, reasons = _score_case(query, case)
        results.append(CaseSimilarity(case_id=case["case_id"], score=score, reasons=reasons))
    results.sort(key=lambda r: (-r.score, r.case_id))
    if top is not None:
        results = results[:top]
    return results
