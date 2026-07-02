"""Splink model for Equipment dedupe (§8.5)."""

from __future__ import annotations

import splink.comparison_library as cl
from splink import block_on

from kg_er.blocking import blocking_rules_for
from kg_er.models.base import ModelSpec


def equipment_spec() -> ModelSpec:
    return ModelSpec(
        entity_type="Equipment",
        comparisons=[
            cl.JaroWinklerAtThresholds("name_clean", [0.9, 0.8]),
            cl.ExactMatch("manufacturer").configure(term_frequency_adjustments=True),
            cl.JaroWinklerAtThresholds("model_code", [0.9]),
        ],
        blocking_rules=blocking_rules_for("Equipment"),
        deterministic_rules=[block_on("manufacturer", "model_code")],
        em_training_blocks=[block_on("manufacturer"), block_on("name_clean")],
    )
