"""5-way gap taxonomy (§ M12).

A flat ``gap_type`` string ("missing_baseline", "contradictory_measurements", …) tells
*what kind* of hole was found, but not *how to read its absence*. For a research lead the
strategically useful distinction is a 5-way one:

- ``KNOWN``                    — знание присутствует (не пробел);
- ``WEAK_EVIDENCE``            — данные есть, но слабые/спорные;
- ``CONTRADICTED``            — источники противоречат друг другу;
- ``POSSIBLE_EXTRACTION_GAP``  — вероятно, факт есть в источнике, но не извлечён;
- ``TRUE_GAP``                — настоящий пробел в знаниях.

This module is a pure, self-contained mapping (no store, no I/O, no heavy imports) so it
can be called from any service that already has a ``gap_type`` in hand.
"""

from __future__ import annotations

# Canonical codes → Russian UI label.
TAXONOMY5_RU: dict[str, str] = {
    "KNOWN": "известно",
    "WEAK_EVIDENCE": "слабые данные",
    "CONTRADICTED": "противоречие",
    "POSSIBLE_EXTRACTION_GAP": "возможно, пропуск извлечения",
    "TRUE_GAP": "настоящий пробел",
}

# gap_type values that mean "the evidence exists but is thin / disputed".
_WEAK = {
    "unverified_claim",
    "low_coverage_material",
    "low_confidence_entity_resolution",
}


def classify_gap_5way(
    gap_type: str | None, absence_confidence: float | None = None
) -> tuple[str, str]:
    """Map a raw ``gap_type`` (+ optional absence confidence) to a 5-way code and RU label.

    Returns ``(code, ru_label)``. Precedence is deliberate:

    1. sentinel "covered"/None-ish that means *not a gap*  → ``KNOWN``;
    2. ``contradictory_measurements``                      → ``CONTRADICTED``;
    3. weak-evidence family (unverified / low-coverage / low-confidence ER) → ``WEAK_EVIDENCE``;
    4. ``missing_source_span`` OR absence_confidence < 0.5  → ``POSSIBLE_EXTRACTION_GAP``;
    5. everything else (missing_*, orphan_entity, only_foreign_sources, unknown) → ``TRUE_GAP``.

    Note: a Gap node with ``gap_type`` None/"" is an *unclassified* gap, so it falls through
    to ``TRUE_GAP``. The explicit ``KNOWN`` branch only fires on the "covered" sentinel — a
    node that was checked and found to already hold the knowledge.
    """
    gt = (gap_type or "").strip()

    if gt == "covered":
        return "KNOWN", TAXONOMY5_RU["KNOWN"]
    if gt == "contradictory_measurements":
        return "CONTRADICTED", TAXONOMY5_RU["CONTRADICTED"]
    if gt in _WEAK:
        return "WEAK_EVIDENCE", TAXONOMY5_RU["WEAK_EVIDENCE"]
    if gt == "missing_source_span" or (
        absence_confidence is not None and absence_confidence < 0.5
    ):
        return "POSSIBLE_EXTRACTION_GAP", TAXONOMY5_RU["POSSIBLE_EXTRACTION_GAP"]
    return "TRUE_GAP", TAXONOMY5_RU["TRUE_GAP"]
