"""Chemical-reaction extraction from prose (§6.12).

Извлечение химических реакций из текста (чистый Python, только regex).

Finds inorganic reaction equations in RU/EN text and returns structured
:class:`Reaction` records (evidence-first, deterministic, dependency-light).

A reaction is a run of *species* separated by ``+`` on each side of an arrow.
Three arrow forms are recognized: ASCII ``->``, the plain ``=`` (common in
Russian chemistry notation) and the Unicode arrow ``→``. Examples::

    "2Cu2S + 3O2 -> 2Cu2O + 2SO2"   # EN, roasting of chalcocite
    "CuFeS2 + O2 = Cu2S + SO2"       # RU-notation "="

Each species is a chemical formula optionally prefixed by a stoichiometric
coefficient. The coefficient (a leading integer) is stripped from the stored
species, so ``2Cu2S`` becomes ``Cu2S`` while the subscript ``2`` is preserved.

Every element symbol in every species is validated against a small curated
element set (:data:`_ELEMENTS`); a candidate whose species contain an unknown
symbol (e.g. ``Xx``) is rejected, so ordinary prose never yields a reaction.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------
# Curated (small) element set used to validate species tokens.
# Малый набор символов элементов для валидации формул.
# Covers the common inorganic / metallurgical elements that appear in reaction
# equations; junk two-letter tokens (``Xx``) are rejected against it.
# ---------------------------------------------------------------------------
_ELEMENTS: frozenset[str] = frozenset(
    [
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
        "Ag",
        "Cd",
        "Sn",
        "Sb",
        "I",
        "Ba",
        "W",
        "Pt",
        "Au",
        "Hg",
        "Pb",
        "Bi",
    ]
)

# A species: optional leading coefficient, then one or more element+subscript
# groups. The subscript digits belong to the formula and are NOT the coefficient.
_SPECIES = r"\d*(?:[A-Z][a-z]?\d*)+"
# One side of a reaction: species joined by "+".
_SIDE = rf"{_SPECIES}(?:\s*\+\s*{_SPECIES})*"
# Arrow forms: ASCII "->", Unicode "→" and the plain "=".
_ARROW = r"->|→|="
_REACTION_RE = re.compile(rf"({_SIDE})\s*({_ARROW})\s*({_SIDE})")

# A well-formed formula (coefficient already removed) and its element tokens.
_FORMULA_RE = re.compile(r"(?:[A-Z][a-z]?\d*)+")
_ELEM_RE = re.compile(r"[A-Z][a-z]?")
_COEFF_RE = re.compile(r"^\d+")


@dataclass(frozen=True)
class Reaction:
    """A parsed chemical reaction equation (§6.12).

    Разобранное уравнение химической реакции.
    """

    reactants: list[str]
    products: list[str]
    arrow: str
    source_span: str

    def as_dict(self) -> dict:
        """Serialize to a plain dict (all fields preserved)."""
        return asdict(self)


def _strip_coeff(species: str) -> str:
    """Drop the leading stoichiometric coefficient, keeping subscripts intact."""
    return _COEFF_RE.sub("", species.strip())


def _is_valid_formula(formula: str) -> bool:
    """True when ``formula`` is element+subscript tokens over the element set."""
    if not formula or not _FORMULA_RE.fullmatch(formula):
        return False
    return all(sym in _ELEMENTS for sym in _ELEM_RE.findall(formula))


def _split_side(side: str) -> list[str] | None:
    """Split a reaction side on ``+`` into validated, coefficient-free species.

    Returns ``None`` if any species is not a valid formula.
    """
    species: list[str] = []
    for raw in side.split("+"):
        formula = _strip_coeff(raw)
        if not _is_valid_formula(formula):
            return None
        species.append(formula)
    return species or None


def extract_reactions(text: str) -> list[Reaction]:
    """Extract all chemical reactions from ``text`` (empty list if none).

    Извлечение всех химических реакций из текста; ``[]`` если реакций нет.
    """
    if not text:
        return []
    out: list[Reaction] = []
    for m in _REACTION_RE.finditer(text):
        reactants = _split_side(m.group(1))
        products = _split_side(m.group(3))
        if reactants is None or products is None:
            continue  # a species failed element validation — not a real reaction
        out.append(Reaction(reactants, products, m.group(2), m.group(0)))
    return out
