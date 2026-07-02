"""Splink model for Person dedupe (§8.5).

ORCID exact match is a strong signal; otherwise family_name + given-initial +
email domain. Term-frequency adjustment on family_name so common surnames
(Ivanov/Smith) contribute less.
"""

from __future__ import annotations

import splink.comparison_library as cl
from splink import block_on

from kg_er.blocking import blocking_rules_for
from kg_er.models.base import ModelSpec


def person_spec() -> ModelSpec:
    return ModelSpec(
        entity_type="Person",
        comparisons=[
            cl.ExactMatch("orcid"),  # ORCID exact is the strongest identity signal
            cl.JaroWinklerAtThresholds("family_name", [0.92, 0.85]).configure(
                term_frequency_adjustments=True
            ),
            cl.ExactMatch("given_initial"),
            cl.ExactMatch("email_domain").configure(term_frequency_adjustments=True),
        ],
        blocking_rules=blocking_rules_for("Person"),
        deterministic_rules=[block_on("orcid"), block_on("family_name", "given_name")],
        em_training_blocks=[block_on("family_name"), block_on("given_initial")],
    )
