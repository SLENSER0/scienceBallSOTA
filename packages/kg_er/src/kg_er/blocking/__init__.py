"""Per-type Splink blocking rules (§8.3)."""

from __future__ import annotations

from splink import block_on

# Blocking rules per entity type. Each keeps the cartesian product small while
# preserving recall; §8.3 requires >=2 complementary blocks per type so a single
# noisy field does not drop true pairs.
BLOCKING_RULES: dict[str, list] = {
    "Material": [block_on("element_key"), block_on("designation_code"), block_on("alloy_family")],
    "Equipment": [block_on("manufacturer"), block_on("model_code")],
    "Person": [block_on("family_name", "given_initial"), block_on("orcid")],
    "Lab": [block_on("org_token"), block_on("country")],
    "ResearchTeam": [block_on("org_token"), block_on("country")],
}


def blocking_rules_for(entity_type: str) -> list:
    """Return blocking rules for *entity_type* (raises for unknown types)."""
    if entity_type not in BLOCKING_RULES:
        raise KeyError(f"no blocking rules for entity type {entity_type!r}")
    return BLOCKING_RULES[entity_type]
