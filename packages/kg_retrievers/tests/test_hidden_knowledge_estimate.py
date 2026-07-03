"""Tests for the corpus-level hidden-knowledge estimate (§25.10).

RU: Проверки оценки скрытого знания. EN: Checks for the hidden-knowledge estimate.
"""

from __future__ import annotations

from kg_retrievers.hidden_knowledge_estimate import (
    HiddenKnowledgeEstimate,
    estimate_hidden_knowledge,
)

_CELLS = [
    {"p_extractor_missed": 0.6, "modality": "prose", "material": "X"},
    {"p_extractor_missed": 0.4, "modality": "prose", "material": "Y"},
    {"p_extractor_missed": 0.9, "modality": "table_row", "material": "X"},
]


def test_expected_missed_facts_total() -> None:
    est = estimate_hidden_knowledge(_CELLS)
    assert round(est.expected_missed_facts, 1) == 1.9
    assert est.n_cells == 3


def test_modality_breakdown() -> None:
    est = estimate_hidden_knowledge(_CELLS)
    assert round(est.by_modality["prose"], 1) == 1.0
    assert est.by_modality["table_row"] == 0.9


def test_top_material_is_summed_max() -> None:
    # X = 0.6 + 0.9 = 1.5 beats Y = 0.4.
    est = estimate_hidden_knowledge(_CELLS)
    assert est.top_material == "X"


def test_modality_sum_equals_total() -> None:
    est = estimate_hidden_knowledge(_CELLS)
    assert sum(est.by_modality.values()) == est.expected_missed_facts


def test_empty_cells() -> None:
    est = estimate_hidden_knowledge([])
    assert est.expected_missed_facts == 0.0
    assert est.n_cells == 0
    assert est.top_material is None
    assert est.by_modality == {}


def test_probabilities_clamped_above_one() -> None:
    cells = [{"p_extractor_missed": 1.7, "modality": "prose", "material": "Z"}]
    est = estimate_hidden_knowledge(cells)
    assert est.expected_missed_facts == 1.0
    assert est.by_modality["prose"] == 1.0


def test_negative_probability_clamped_to_zero() -> None:
    cells = [{"p_extractor_missed": -0.5, "modality": "prose", "material": "Z"}]
    est = estimate_hidden_knowledge(cells)
    assert est.expected_missed_facts == 0.0


def test_frozen_dataclass_and_as_dict() -> None:
    est = estimate_hidden_knowledge(_CELLS)
    assert isinstance(est, HiddenKnowledgeEstimate)
    payload = est.as_dict()
    assert payload["n_cells"] == 3
    assert payload["top_material"] == "X"
    assert round(payload["expected_missed_facts"], 1) == 1.9
    assert set(payload) >= {
        "schema_version",
        "expected_missed_facts",
        "n_cells",
        "by_modality",
        "top_material",
    }
