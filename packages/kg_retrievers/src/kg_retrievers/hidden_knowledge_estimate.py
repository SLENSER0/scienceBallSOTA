"""Corpus-level hidden-knowledge estimate (§25.10).

RU: Оценка объёма скрытого знания, которое корпус содержит, но экстракция
    пропустила, суммированием пофактовых вероятностей пропуска по near-miss ячейкам.
EN: Corpus-level estimate of how many facts the corpus contains but extraction
    missed, by summing per-cell ``p_extractor_missed`` over near-miss cells.

Each near-miss cell carries ``p_extractor_missed`` — the probability that this
cell hides a real fact the extractor failed to capture (a Bernoulli mean). Under
the expected-count interpretation, summing that probability over all cells yields
the *expected* number of missed facts in the corpus. Grouping the sum by modality
and by material tells us *where* the hidden knowledge concentrates: which
extraction modality (prose, table row, …) leaks the most facts, and which
material accumulates the largest missed-fact backlog.

Probabilities are clamped to ``[0.0, 1.0]`` so a malformed ``p > 1`` counts as a
single expected fact and a negative value contributes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "0.1.0"


def _clamp(value: object) -> float:
    """Clamp a probability into ``[0.0, 1.0]``; non-numbers → ``0.0``.

    RU: приводит вероятность к отрезку [0, 1]. EN: clamp probability to [0, 1].
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    p = float(value)
    if p < 0.0:
        return 0.0
    if p > 1.0:
        return 1.0
    return p


@dataclass(frozen=True, slots=True)
class HiddenKnowledgeEstimate:
    """Corpus-level hidden-knowledge estimate (§25.10).

    RU: ожидаемое число пропущенных фактов с разбивкой по модальности/материалу.
    EN: expected number of missed facts with modality / material breakdowns.
    """

    expected_missed_facts: float
    n_cells: int
    by_modality: dict[str, float]
    top_material: str | None

    def as_dict(self) -> dict[str, object]:
        """RU: сериализация в словарь. EN: serialise to a plain dict."""
        return {
            "schema_version": SCHEMA_VERSION,
            "expected_missed_facts": self.expected_missed_facts,
            "n_cells": self.n_cells,
            "by_modality": dict(self.by_modality),
            "top_material": self.top_material,
        }


def estimate_hidden_knowledge(cells: list[dict]) -> HiddenKnowledgeEstimate:
    """Sum per-cell ``p_extractor_missed`` into a hidden-knowledge estimate (§25.10).

    RU: суммирует p_extractor_missed по модальностям и материалам, находит топ-материал.
    EN: sums p_extractor_missed by modality and material, finds the top material.
    """
    expected = 0.0
    by_modality: dict[str, float] = {}
    by_material: dict[str, float] = {}

    for cell in cells:
        p = _clamp(cell.get("p_extractor_missed"))
        expected += p
        modality = str(cell.get("modality", ""))
        material = str(cell.get("material", ""))
        by_modality[modality] = by_modality.get(modality, 0.0) + p
        by_material[material] = by_material.get(material, 0.0) + p

    top_material: str | None = None
    if by_material:
        # RU: материал с наибольшей суммой; EN: material with the largest sum.
        top_material = max(by_material, key=lambda m: by_material[m])

    return HiddenKnowledgeEstimate(
        expected_missed_facts=expected,
        n_cells=len(cells),
        by_modality=by_modality,
        top_material=top_material,
    )
