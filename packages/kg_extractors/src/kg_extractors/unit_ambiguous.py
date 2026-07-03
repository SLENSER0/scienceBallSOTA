"""Ambiguous-unit detection for composition/concentration values (§7.6).

Closes an audit gap: a bare ``%`` in a composition context (``"2.5 %"``) is
*undetected* by the shape-based problem classifier of
:mod:`kg_extractors.unit_problems` — pint happily parses ``%`` as ``percent``,
so it is neither missing nor unparseable, yet the *basis* (weight / atomic /
volume) is unspecified and the number is scientifically ambiguous (неоднозначная
единица: базис не указан).

This module diagnoses that class of problem for one extracted value string:

* a bare ``%`` in a composition context is **ambiguous** — candidates are
  ``wt%`` / ``at%`` / ``vol%`` (масс./ат./об. %);
* a bare ``ppm`` (or ``ppb``) without a basis is **ambiguous** — candidates are
  ``wt ppm`` / ``at ppm`` / ``vol ppm`` (mass / atomic / volume basis);
* a fully-qualified ``wt%`` / ``at%`` / ``об.%`` / ``ppmw`` is **not** ambiguous;
* a fully-specified physical unit (``mg/L``, ``m/s``) is **not** ambiguous;
* a bare ``%`` in a *non*-composition context (recovery / yield / efficiency)
  is **not** ambiguous — it is a plain percentage (проценты извлечения), so the
  detector returns ``None`` there (documented behaviour).

Reuses the *problem-token* style of :mod:`kg_extractors.unit_problems` (a module
this one does **not** edit) — see :data:`AMBIGUOUS_UNIT`. Pure Python — no LLM,
no I/O.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --- problem token (проблема), §7.6 ------------------------------------------
#: Problem token for a unit whose basis is unspecified (неоднозначная единица).
AMBIGUOUS_UNIT = "ambiguous_unit"

# --- disambiguation vocabulary (базисы) --------------------------------------
#: Basis prefixes offered as candidates for a bare fraction unit (масс./ат./об.).
_BASIS_LABELS: tuple[str, str, str] = ("wt", "at", "vol")

#: Candidate qualified percents for a bare ``%`` — ``wt%`` / ``at%`` / ``vol%``.
PERCENT_CANDIDATES: tuple[str, ...] = tuple(f"{b}%" for b in _BASIS_LABELS)

#: Candidate qualified ppm for a bare ``ppm`` — ``wt ppm`` / ``at ppm`` / ``vol ppm``.
PPM_CANDIDATES: tuple[str, ...] = tuple(f"{b} ppm" for b in _BASIS_LABELS)

#: Basis markers that DISAMBIGUATE a ``%`` / ``ppm`` (EN + RU): presence ⇒ not ambiguous.
_BASES: tuple[str, ...] = (
    "wt",
    "at",
    "vol",
    "mol",
    "mass",
    "atomic",
    "wgt",  # EN (весовой/атомный/объёмный)
    "мас",
    "масс",
    "ат",
    "об",
    "объ",  # RU (масс. / ат. / об.)
)

#: Single-letter ppm/ppb basis suffixes — ``ppmw`` / ``ppma`` / ``ppmv``.
_PPM_SUFFIXES: frozenset[str] = frozenset({"w", "a", "v"})

#: Property-context substrings that mark a *composition* value (состав/концентрация).
_COMPOSITION_CONTEXTS: tuple[str, ...] = (
    "composition",
    "concentration",
    "content",
    "assay",
    "impurity",
    "dopant",
    "doping",
    "alloy",
    "состав",
    "концентрац",
    "содержан",
    "примес",
    "сплав",
)

#: Strips a leading numeric constraint (``2.5``, ``≤1000``) off a value string.
_LEADING_NUM = re.compile(r"^\s*[<>≤≥⩽⩾≈~=]*\s*[-+]?\d+(?:[.,]\d+)?\s*")


@dataclass(frozen=True)
class AmbiguityFlag:
    """A unit whose *basis* is unspecified (§7.6).

    Fields
    ------
    kind
        Always :data:`AMBIGUOUS_UNIT` (тип проблемы).
    unit
        The bare unit token as found, e.g. ``"%"`` or ``"ppm"`` (найденная единица).
    candidates
        Ordered disambiguated units the curator should pick from
        (варианты: ``wt%`` / ``at%`` / ``vol%``).
    reason
        Human-readable explanation (RU/EN) of why the unit is ambiguous.
    """

    kind: str
    unit: str
    candidates: list[str]
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "kind": self.kind,
            "unit": self.unit,
            "candidates": list(self.candidates),
            "reason": self.reason,
        }


def _norm_unit(unit: str) -> str:
    """Fold a unit token for basis matching: NFKC, lower, drop spaces/dots/middots."""
    s = unicodedata.normalize("NFKC", unit).strip().lower()
    return s.replace(" ", "").replace(".", "").replace("·", "")


def _extract_unit(value_str: str) -> str:
    """Strip the leading number/operator off *value_str*, leaving the unit token."""
    s = unicodedata.normalize("NFKC", value_str or "").strip()
    if not s:
        return ""
    m = _LEADING_NUM.match(s)
    return s[m.end() :].strip() if m else s


def _classify_unit(unit: str) -> tuple[str | None, str]:
    """Return ``(family, rest)`` — family ``"percent"``/``"ppm"``/``None`` + basis part."""
    n = _norm_unit(unit)
    if not n:
        return None, ""
    if "ppm" in n or "ppb" in n:
        return "ppm", n.replace("ppm", "").replace("ppb", "")
    if "%" in n or "percent" in n:
        return "percent", n.replace("%", "").replace("percent", "")
    return None, ""


def _basis_present(rest: str) -> bool:
    """True iff *rest* (unit minus its ``%``/``ppm`` core) names a known basis."""
    if not rest:
        return False
    if rest in _PPM_SUFFIXES:  # ppmw / ppma / ppmv
        return True
    return any(base in rest for base in _BASES)


def _is_composition_context(property_context: object) -> bool:
    """True iff *property_context* names a composition/concentration value (§7.6)."""
    ctx = str(property_context or "").lower()
    return any(key in ctx for key in _COMPOSITION_CONTEXTS)


def _reason(family: str, unit: str) -> str:
    """Human-readable ambiguity reason (RU/EN)."""
    basis = "mass/atomic/volume" if family == "ppm" else "wt/at/vol"
    return (
        f"bare '{unit}' has no {basis} basis (базис не указан) — ambiguous in a composition context"
    )


def candidate_units(unit: str, property_context: object) -> list[str]:
    """Disambiguated units for a bare fraction *unit* in *property_context* (§7.6).

    Returns the ordered list a curator should choose from — ``["wt%", "at%",
    "vol%"]`` for a bare ``%`` (``["wt ppm", ...]`` for a bare ``ppm``/``ppb``) —
    but only when the unit is genuinely ambiguous: a bare ``%``/``ppm`` with no
    basis marker *and* a composition context. Returns ``[]`` for a qualified
    unit (``wt%``, ``ppmw``), a non-fraction unit (``mg/L``), or a
    non-composition context (recovery). Pure function, mirrors the token style of
    :mod:`kg_extractors.unit_problems`.
    """
    family, rest = _classify_unit(unit)
    if family is None or _basis_present(rest):
        return []
    if not _is_composition_context(property_context):
        return []
    if family == "percent":
        return [f"{b}%" for b in _BASIS_LABELS]
    core = "ppb" if "ppb" in _norm_unit(unit) else "ppm"
    return [f"{b} {core}" for b in _BASIS_LABELS]


def detect_ambiguous_unit(
    value_str: str,
    property_context: object = None,
) -> AmbiguityFlag | None:
    """Detect a basis-ambiguous unit in *value_str* (§7.6).

    Parses the unit token off *value_str* (``"2.5 %"`` → ``"%"``) and, using the
    property's *context*, decides whether its basis is unspecified. A bare
    ``%``/``ppm`` in a composition context yields an :class:`AmbiguityFlag`
    carrying the disambiguation candidates; a qualified unit (``wt%``), a
    fully-specified unit (``mg/L``), an empty string, or a non-composition
    context (recovery) yields ``None``. Pure function — no LLM, no I/O.
    """
    unit = _extract_unit(value_str)
    if not unit:
        return None
    candidates = candidate_units(unit, property_context)
    if not candidates:
        return None
    family, _rest = _classify_unit(unit)
    return AmbiguityFlag(
        kind=AMBIGUOUS_UNIT,
        unit=unit,
        candidates=candidates,
        reason=_reason(family or "percent", unit),
    )


__all__ = [
    "AMBIGUOUS_UNIT",
    "PERCENT_CANDIDATES",
    "PPM_CANDIDATES",
    "AmbiguityFlag",
    "candidate_units",
    "detect_ambiguous_unit",
]
