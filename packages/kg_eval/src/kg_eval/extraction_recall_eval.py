"""Modality-attributed extraction recall against a gold fact set (§25.16).

Пер-модальность recall: сколько ожидаемых (gold) фактов реально были извлечены,
разбитых по модальности источника (table_row, chunk, catalog_row, ...). Это ловит
«слепые зоны» (blind spots) — модальности, из которых экстрактор систематически ничего
не достаёт, даже когда общий recall выглядит приемлемым.

Matching model: a gold fact is *matched* iff its ``fact_id`` appears in the set of
extracted ``fact_id``s. Duplicate extracted ids collapse into a set, so a fact is never
double-counted. Per-modality recall is ``matched / n_expected`` (``0.0`` when the group is
empty); ``overall_recall`` is ``total_matched / total_expected`` (``0.0`` on empty gold).

Blind spots: modalities whose recall falls *strictly below* ``blind_spot_at`` (default
``0.5``), returned sorted for a stable report. A modality never present in gold does not
appear in ``by_modality`` at all — we only measure what we expected to find.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


def attribute_modality(evidence: dict) -> str:
    """Derive a modality label from an evidence/fact row.

    Prefers an explicit ``modality`` key, falls back to ``kind``, and otherwise
    returns ``"unknown"`` — so untagged evidence is bucketed rather than dropped.
    """
    return evidence.get("modality") or evidence.get("kind") or "unknown"


@dataclass(frozen=True)
class ModalityRecall:
    """Recall for a single source modality (§25.16).

    ``recall`` is ``n_extracted / n_expected`` in ``[0.0, 1.0]`` (``0.0`` when
    ``n_expected == 0``); ``n_extracted`` is the count of *matched* gold facts.
    """

    modality: str
    n_expected: int
    n_extracted: int
    recall: float

    def as_dict(self) -> dict[str, str | int | float]:
        return {
            "modality": self.modality,
            "n_expected": self.n_expected,
            "n_extracted": self.n_extracted,
            "recall": round(self.recall, 4),
        }


@dataclass(frozen=True)
class ExtractionRecallReport:
    """Modality-attributed extraction recall report (§25.16).

    ``by_modality`` holds one :class:`ModalityRecall` per gold modality; ``blind_spots``
    lists modalities whose recall is below the threshold, sorted for stability.
    """

    by_modality: list[ModalityRecall]
    overall_recall: float
    n_expected: int
    n_extracted: int
    blind_spots: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "by_modality": [m.as_dict() for m in self.by_modality],
            "overall_recall": round(self.overall_recall, 4),
            "n_expected": self.n_expected,
            "n_extracted": self.n_extracted,
            "blind_spots": list(self.blind_spots),
        }


def evaluate_extraction_recall(
    gold: list[dict], extracted: list[dict], *, blind_spot_at: float = 0.5
) -> ExtractionRecallReport:
    """Score modality-attributed extraction recall of ``extracted`` against ``gold``.

    ``gold`` rows carry ``{"fact_id", "modality"}``; ``extracted`` rows carry
    ``{"fact_id"}``. A gold fact is matched iff its id is in the extracted id set, so
    duplicate extracted ids never inflate the match count. Recall is computed per gold
    modality and overall; modalities below ``blind_spot_at`` become ``blind_spots``.
    """
    extracted_ids = {row["fact_id"] for row in extracted}

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in gold:
        grouped[attribute_modality(row)].append(row)

    by_modality: list[ModalityRecall] = []
    total_expected = 0
    total_matched = 0
    for modality in sorted(grouped):
        rows = grouped[modality]
        n_expected = len(rows)
        matched = sum(1 for r in rows if r["fact_id"] in extracted_ids)
        recall = matched / n_expected if n_expected else 0.0
        by_modality.append(ModalityRecall(modality, n_expected, matched, recall))
        total_expected += n_expected
        total_matched += matched

    overall = total_matched / total_expected if total_expected else 0.0
    blind_spots = sorted(m.modality for m in by_modality if m.recall < blind_spot_at)
    return ExtractionRecallReport(
        by_modality=by_modality,
        overall_recall=overall,
        n_expected=total_expected,
        n_extracted=total_matched,
        blind_spots=blind_spots,
    )
