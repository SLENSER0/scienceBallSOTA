"""Splink model for Material/Alloy dedupe (§8.4).

Comparisons: name (jaro-winkler levels), normalized_formula (exact + composition
distance), element_set (Jaccard-ish exact on element_key), designation_code
(exact). Handles both ``Material`` and ``Alloy`` labels as one entity space.
"""

from __future__ import annotations

import splink.comparison_library as cl
from splink import block_on

from kg_er.blocking import blocking_rules_for
from kg_er.models.base import ModelSpec


def material_spec() -> ModelSpec:
    return ModelSpec(
        entity_type="Material",
        comparisons=[
            cl.JaroWinklerAtThresholds("name_clean", [0.92, 0.85]),
            cl.CustomComparison(
                output_column_name="normalized_formula",
                comparison_levels=[
                    {
                        # empty-string literals use single quotes; "" would be a
                        # zero-length SQL identifier and fail to parse in DuckDB.
                        "sql_condition": (
                            "\"normalized_formula_l\" = '' "
                            "OR \"normalized_formula_r\" = ''"
                        ),
                        "label_for_charts": "null/empty",
                        "is_null_level": True,
                    },
                    {
                        "sql_condition": '"normalized_formula_l" = "normalized_formula_r"',
                        "label_for_charts": "exact formula",
                    },
                    {
                        "sql_condition": '"element_key_l" = "element_key_r"',
                        "label_for_charts": "same elements",
                    },
                    {"sql_condition": "ELSE", "label_for_charts": "different"},
                ],
            ),
            cl.ExactMatch("designation_code").configure(term_frequency_adjustments=True),
        ],
        blocking_rules=blocking_rules_for("Material"),
        deterministic_rules=[
            block_on("normalized_formula"),
            block_on("designation_code"),
        ],
        em_training_blocks=[block_on("element_key"), block_on("name_clean")],
        retain_intermediate=True,
    )
