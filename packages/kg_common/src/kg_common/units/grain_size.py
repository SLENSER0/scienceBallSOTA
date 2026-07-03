"""ASTM E112 grain-size number ↔ mean grain diameter (§7.2).

Metallurgy grain-size relation, canonical target ``um`` (micrometre).
The ASTM E112 grain-size number ``G`` is defined via the number of grains
per square millimetre at 1X magnification::

    N_A = 2 ** (G - 1) * 15.500        # grains / mm² at 1X
    d   = sqrt(1 / N_A)                # mean grain diameter (mm)

A *finer* microstructure (more, smaller grains) has a *larger* ``G`` and a
*smaller* mean diameter. This module gives the forward and inverse maps plus a
frozen :class:`GrainSize` record for downstream normalisation. Pure stdlib.

Метрика размера зерна ASTM E112: номер зерна ``G`` ↔ средний диаметр (мкм).
Чем мельче зерно, тем больше ``G`` и меньше диаметр.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

# Grains per mm² at 1X for G = 1 (base of the ASTM E112 geometric progression).
N_A_AT_G1: float = 15.500


@dataclass(frozen=True)
class GrainSize:
    """A single grain-size observation across ASTM E112 representations.

    Наблюдение размера зерна в разных представлениях ASTM E112.
    """

    astm_g: float | None
    diameter_um: float | None
    grains_per_mm2: float | None

    def as_dict(self) -> dict[str, float | None]:
        """Return a plain dict (JSON-friendly) of all fields."""
        return asdict(self)


def _grains_per_mm2(g: float) -> float:
    """N_A = 2**(G-1) * 15.500 — grains per mm² at 1X for grain number *g*."""
    return 2.0 ** (g - 1.0) * N_A_AT_G1


def astm_g_to_diameter_um(g: float) -> float:
    """Mean grain diameter (µm) for ASTM E112 grain-size number *g*.

    d = sqrt(1 / N_A) in mm, converted to µm (×1000).
    """
    n_a = _grains_per_mm2(g)  # grains / mm²
    d_mm = math.sqrt(1.0 / n_a)
    return d_mm * 1000.0


def diameter_um_to_astm_g(d_um: float) -> float:
    """ASTM E112 grain-size number *G* for a mean grain diameter (µm).

    Inverse of :func:`astm_g_to_diameter_um`:
    ``G = 1 + log2(1e6 / (d_um**2 * 15.500))``.
    """
    if d_um <= 0.0:
        raise ValueError(f"diameter_um must be positive, got {d_um!r}")
    return 1.0 + math.log2(1.0e6 / (d_um**2 * N_A_AT_G1))


def grain_size_from_g(g: float) -> GrainSize:
    """Build a :class:`GrainSize` from an ASTM E112 grain-size number *g*."""
    return GrainSize(
        astm_g=g,
        diameter_um=astm_g_to_diameter_um(g),
        grains_per_mm2=_grains_per_mm2(g),
    )
