"""Materials-property unit helpers (§7).

Complements the domain unit normalizer in ``kg_extractors.units`` (mining/water
units: A/m², mg/L, m/s) with metallurgy hardness/strength conversions used to
compare measurements reported on different scales.
"""

from __future__ import annotations

from kg_common.units.hardness import (
    HARDNESS_SCALES,
    HardnessConversion,
    convert_hardness,
    hv_to_tensile_mpa,
)

__all__ = [
    "HARDNESS_SCALES",
    "HardnessConversion",
    "convert_hardness",
    "hv_to_tensile_mpa",
]
