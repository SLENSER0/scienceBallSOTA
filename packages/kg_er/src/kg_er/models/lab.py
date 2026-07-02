"""Splink model for Lab / ResearchTeam dedupe (§8.5)."""

from __future__ import annotations

import splink.comparison_library as cl
from splink import block_on

from kg_er.blocking import blocking_rules_for
from kg_er.models.base import ModelSpec


def lab_spec(entity_type: str = "Lab") -> ModelSpec:
    return ModelSpec(
        entity_type=entity_type,
        comparisons=[
            cl.JaroWinklerAtThresholds("org", [0.9, 0.8]).configure(
                term_frequency_adjustments=True
            ),
            cl.JaroWinklerAtThresholds("name_clean", [0.9, 0.8]),
            cl.ExactMatch("city"),
            cl.ExactMatch("country").configure(term_frequency_adjustments=True),
        ],
        blocking_rules=blocking_rules_for(entity_type),
        deterministic_rules=[block_on("org", "city")],
        em_training_blocks=[block_on("org_token"), block_on("country")],
    )
