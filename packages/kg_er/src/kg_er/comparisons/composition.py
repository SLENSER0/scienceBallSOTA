"""Chemical-composition normalization for Material ER (§8.2/§8.3).

Uses pymatgen (``Composition``, ``Element``) when available for a reduced,
authoritative formula + element set; falls back to a deterministic regex parser
so the package works without the heavy ``materials`` extra installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:  # pragma: no cover - exercised via the has_pymatgen flag in tests
    from pymatgen.core import Composition as _PmgComposition

    HAS_PYMATGEN = True
except Exception:  # pragma: no cover
    _PmgComposition = None
    HAS_PYMATGEN = False

_ELEMENT_RE = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")
# Known element symbols so the fallback parser rejects junk like "Xx".
_ELEMENTS = {
    "H",
    "He",
    "Li",
    "Be",
    "B",
    "C",
    "N",
    "O",
    "F",
    "Ne",
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "S",
    "Cl",
    "Ar",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Ge",
    "As",
    "Se",
    "Br",
    "Kr",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
    "Sn",
    "Sb",
    "Te",
    "I",
    "Xe",
    "Cs",
    "Ba",
    "La",
    "Ce",
    "Pr",
    "Nd",
    "Pm",
    "Sm",
    "Eu",
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Lu",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
    "Tl",
    "Pb",
    "Bi",
    "Po",
    "At",
    "Rn",
    "Th",
    "U",
    "Pu",
}


@dataclass(frozen=True)
class NormalizedComposition:
    reduced_formula: str
    element_set: frozenset[str]
    fractions: tuple[tuple[str, float], ...]  # sorted (element, atomic_fraction)

    @property
    def element_key(self) -> str:
        """Stable key = sorted element symbols joined, e.g. "Cr-Fe-Ni"."""
        return "-".join(sorted(self.element_set))


def _fallback_parse(formula: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for sym, num in _ELEMENT_RE.findall(formula or ""):
        if sym not in _ELEMENTS:
            continue
        counts[sym] = counts.get(sym, 0.0) + (float(num) if num else 1.0)
    return counts


def normalize_formula(formula: str | None) -> NormalizedComposition | None:
    """Parse a chemical formula into a normalized composition, or None."""
    if not formula or not str(formula).strip():
        return None
    raw = str(formula).strip()
    if HAS_PYMATGEN:
        try:
            comp = _PmgComposition(raw)
            total = comp.num_atoms or 1.0
            fractions = {str(el): amt / total for el, amt in comp.get_el_amt_dict().items()}
            reduced = comp.reduced_formula
            elements = frozenset(str(el) for el in comp.elements)
            return NormalizedComposition(
                reduced_formula=reduced,
                element_set=elements,
                fractions=tuple(sorted(fractions.items())),
            )
        except Exception:
            pass  # fall through to regex parser on malformed input
    counts = _fallback_parse(raw)
    if not counts:
        return None
    total = sum(counts.values()) or 1.0
    fractions = {el: n / total for el, n in counts.items()}
    reduced = "".join(
        f"{el}{_fmt(counts[el])}" for el in sorted(counts, key=lambda e: (-counts[e], e))
    )
    return NormalizedComposition(
        reduced_formula=reduced,
        element_set=frozenset(counts),
        fractions=tuple(sorted(fractions.items())),
    )


def _fmt(n: float) -> str:
    return "" if abs(n - 1.0) < 1e-9 else (str(int(n)) if float(n).is_integer() else f"{n:g}")


def composition_distance(a: str | None, b: str | None) -> float:
    """L1 distance over atomic fractions in [0, 1] (0 = identical, 1 = disjoint).

    Used as a Splink comparison level for ``normalized_formula``.
    """
    ca, cb = normalize_formula(a), normalize_formula(b)
    if ca is None or cb is None:
        return 1.0
    da = dict(ca.fractions)
    db = dict(cb.fractions)
    elements = set(da) | set(db)
    return 0.5 * sum(abs(da.get(e, 0.0) - db.get(e, 0.0)) for e in elements)


def element_jaccard(a: str | None, b: str | None) -> float:
    ca, cb = normalize_formula(a), normalize_formula(b)
    if ca is None or cb is None:
        return 0.0
    sa, sb = ca.element_set, cb.element_set
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
