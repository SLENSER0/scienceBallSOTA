"""Non-interconvertible composition-unit family guard (§7.2).

:mod:`kg_common.units.composition_units` performs mass-aware conversion between
composition units *when a full composition is supplied*, but nothing gates
whether a **bare** unit-to-unit conversion is even legal. §7.2 marks the
percent/ppm families — mass fraction (wt%, ppm, ppb) vs. atomic/molar fraction
(at%, mol%) — as **non-interconvertible** without a full composition: you cannot
turn wt% into at% by a fixed factor. This module classifies a unit into its
composition family and rules a conversion allowed only *within* one family.

RU: Барьер для неконвертируемых семейств единиц состава (§7.2). Массовая доля
(wt%, ppm, ppb) и атомная/мольная доля (at%, mol%) не переводятся друг в друга
без полного состава. Конверсия разрешена только внутри одного семейства.
EN: See the description above.

Pure Python, no I/O. Classification only — no numeric conversion is performed.
"""

from __future__ import annotations

from dataclasses import dataclass

#: RU: Единицы массовой доли. EN: Mass-fraction units.
MASS_FRACTION: frozenset[str] = frozenset({"wt_percent", "wt%", "ppm", "ppb"})

#: RU: Единицы атомной/мольной доли. EN: Atomic/molar-fraction units.
ATOMIC_FRACTION: frozenset[str] = frozenset({"at_percent", "at%", "mol_percent"})


@dataclass(frozen=True)
class InterconvertVerdict:
    """Verdict on whether two composition units may be interconverted.

    RU: Вердикт о допустимости взаимной конверсии двух единиц состава.
    EN: Verdict on whether two composition units may be interconverted.
    """

    u1: str
    u2: str
    family1: str | None
    family2: str | None
    allowed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view for JSON/serialisation."""
        return {
            "u1": self.u1,
            "u2": self.u2,
            "family1": self.family1,
            "family2": self.family2,
            "allowed": self.allowed,
            "reason": self.reason,
        }


def composition_family(unit: str) -> str | None:
    """Return the composition family of ``unit`` or ``None`` if it has none.

    RU: Вернуть семейство состава для единицы (``MASS_FRACTION`` /
    ``ATOMIC_FRACTION``) либо ``None``, если единица не относится к составу.
    EN: See above.
    """
    if unit in MASS_FRACTION:
        return "MASS_FRACTION"
    if unit in ATOMIC_FRACTION:
        return "ATOMIC_FRACTION"
    return None


def can_interconvert(u1: str, u2: str) -> InterconvertVerdict:
    """Rule whether ``u1`` and ``u2`` may be interconverted without a composition.

    Allowed only when both units share the *same* composition family. A unit
    outside any composition family (e.g. ``MPa``) can never be interconverted
    with a composition unit.

    RU: Конверсия разрешена только внутри одного семейства состава. Единица вне
    семейств (например, ``MPa``) не конвертируется с единицами состава.
    EN: See above.
    """
    family1 = composition_family(u1)
    family2 = composition_family(u2)

    if family1 is None or family2 is None:
        unknown = u1 if family1 is None else u2
        reason = (
            f"'{unknown}' is not a composition unit; "
            "cross-domain interconversion is undefined (§7.2)"
        )
        return InterconvertVerdict(u1, u2, family1, family2, False, reason)

    if family1 == family2:
        reason = f"both units are in the {family1} family; interconvertible (§7.2)"
        return InterconvertVerdict(u1, u2, family1, family2, True, reason)

    reason = (
        f"'{u1}' is {family1} but '{u2}' is {family2}; families are "
        "non-interconvertible without a full composition (§7.2)"
    )
    return InterconvertVerdict(u1, u2, family1, family2, False, reason)
