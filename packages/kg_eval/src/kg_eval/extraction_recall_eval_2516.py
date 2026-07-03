"""Extraction-recall evaluation by modality via fact→evidence→modality (§25.16).

Пер-модальность recall: доля ожидаемых (gold) фактов, реально извлечённых
экстрактором, с атрибуцией fact→evidence→modality. Каждый gold-факт группируется
по своему полю ``modality`` (table_row, chunk, catalog_row, ...); это ловит «слепые
зоны» (blind spots) — модальности, из которых экстрактор ничего не достаёт, даже
когда общий recall выглядит приемлемым.

Matching model: a gold fact is *extracted* iff some extracted fact shares its
:func:`fact_key` — the tuple ``(doc_id, subject, property_name, value)``. Extracted
keys collapse into a set, so a fact is never double-counted. Per-modality recall is
``extracted / expected`` (``0.0`` when the group is empty); ``overall_recall`` is
``extracted_total / expected_total`` (``0.0`` on empty gold). A modality never present
in gold does not appear in ``by_modality`` — we only measure what we expected to find.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


def fact_key(fact: dict) -> tuple:
    """Identity tuple of a fact: ``(doc_id, subject, property_name, value)``.

    Two facts match iff their keys are equal. Missing keys read as ``None`` so a
    partially-populated row still yields a stable, hashable key rather than raising.
    """
    return (
        fact.get("doc_id"),
        fact.get("subject"),
        fact.get("property_name"),
        fact.get("value"),
    )


@dataclass(frozen=True)
class ModalityRecall:
    """Recall for a single source modality (§25.16).

    ``recall`` is ``extracted / expected`` in ``[0.0, 1.0]`` (``0.0`` when
    ``expected == 0``); ``extracted`` is the count of *matched* gold facts.
    """

    modality: str
    expected: int
    extracted: int
    recall: float

    def as_dict(self) -> dict[str, str | int | float]:
        return {
            "modality": self.modality,
            "expected": self.expected,
            "extracted": self.extracted,
            "recall": round(self.recall, 4),
        }


@dataclass(frozen=True)
class ExtractionRecallReport:
    """Modality-attributed extraction-recall report (§25.16).

    ``by_modality`` holds one :class:`ModalityRecall` per gold modality, keyed by
    modality name; totals aggregate across all modalities.
    """

    by_modality: dict[str, ModalityRecall]
    overall_recall: float
    expected_total: int
    extracted_total: int

    def as_dict(self) -> dict[str, object]:
        return {
            "by_modality": {k: v.as_dict() for k, v in self.by_modality.items()},
            "overall_recall": round(self.overall_recall, 4),
            "expected_total": self.expected_total,
            "extracted_total": self.extracted_total,
        }


def evaluate_extraction_recall(gold: list[dict], extracted: list[dict]) -> ExtractionRecallReport:
    """Score modality-attributed extraction recall of ``extracted`` against ``gold``.

    A gold fact is matched iff its :func:`fact_key` is present in the set of extracted
    keys, so duplicate extracted facts never inflate the match count. Gold facts are
    grouped by their ``modality`` field; recall is computed per modality and overall.
    """
    extracted_keys = {fact_key(row) for row in extracted}

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in gold:
        grouped[str(row.get("modality"))].append(row)

    by_modality: dict[str, ModalityRecall] = {}
    expected_total = 0
    extracted_total = 0
    for modality in sorted(grouped):
        rows = grouped[modality]
        expected = len(rows)
        matched = sum(1 for r in rows if fact_key(r) in extracted_keys)
        recall = matched / expected if expected else 0.0
        by_modality[modality] = ModalityRecall(modality, expected, matched, recall)
        expected_total += expected
        extracted_total += matched

    overall = extracted_total / expected_total if expected_total else 0.0
    return ExtractionRecallReport(
        by_modality=by_modality,
        overall_recall=overall,
        expected_total=expected_total,
        extracted_total=extracted_total,
    )
