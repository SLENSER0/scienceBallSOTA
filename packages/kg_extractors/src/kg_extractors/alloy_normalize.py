"""Alloy-grade string normalization to a stable canonical form (§6.17).

Нормализация строк марок сплавов к канонической форме.

Builds on :func:`kg_extractors.alloy_grades.parse_grade` (reused read-only, never
modified). Three deterministic helpers, regex-free themselves — all recognition is
delegated to :func:`parse_grade`:

- :func:`normalize_grade` — folds a free-text alloy designation (``AA2024`` /
  ``2024-t6`` / ``inconel 718`` / ``Ti-6Al-4V`` / ``316L``) to a single stable
  canonical token (system prefix + standardized ``-`` separators, upper-cased for
  designations without case-sensitive element symbols), or ``None`` when no
  standard grade is present.
- :func:`grade_family` — maps a designation to its broad alloy family
  (``aluminium`` / ``nickel`` / ``titanium`` / ``steel``), or ``None`` when the
  surface carries no recognizable grade.
- :func:`describe_grade` — returns both, plus the underlying system, as a frozen
  :class:`NormalizedGrade`.

The canonical is idempotent: ``normalize_grade(normalize_grade(x)) ==
normalize_grade(x)`` — feeding a canonical token back in returns it unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from kg_extractors.alloy_grades import GradeMatch, parse_grade

# parse_grade system -> broad alloy family (§6.17). British "aluminium" spelling.
_SYSTEM_FAMILY: dict[str, str] = {
    "AA": "aluminium",
    "Inconel": "nickel",
    "Ti": "titanium",
    "AISI": "steel",
}


@dataclass(frozen=True)
class NormalizedGrade:
    """An alloy grade rendered to its canonical token, family and system (§6.17).

    ``canonical`` — the stable normalized designation (``AA2024-T6`` /
    ``INCONEL718`` / ``Ti-6Al-4V`` / ``316L``); ``family`` — one of
    ``aluminium`` / ``nickel`` / ``titanium`` / ``steel``; ``system`` — the raw
    :class:`~kg_extractors.alloy_grades.GradeMatch` system it came from.
    """

    canonical: str
    family: str
    system: str

    def as_dict(self) -> dict[str, str]:
        """Serialize to ``{canonical, family, system}``."""
        return asdict(self)


def _canonical(match: GradeMatch) -> str:
    """Render a :class:`GradeMatch` to its stable canonical token."""
    if match.system == "AA":
        base = f"AA{match.grade}"
        return f"{base}-{match.temper}" if match.temper else base
    if match.system == "Inconel":
        return f"INCONEL{match.grade}"
    # Ti alloys carry case-sensitive element symbols; parse_grade already yields the
    # standard "Ti-6Al-4V" casing with "-" separators, so it is canonical as-is.
    # AISI stainless: the curated bare designation ("316L") is likewise canonical.
    return match.grade


def describe_grade(surface: str) -> NormalizedGrade | None:
    """Parse + normalize an alloy surface, else ``None`` when no grade is present.

    Разбор и нормализация строки марки; ``None``, если марка не распознана.
    """
    match = parse_grade(surface)
    if match is None:
        return None
    return NormalizedGrade(_canonical(match), _SYSTEM_FAMILY[match.system], match.system)


def normalize_grade(surface: str) -> str | None:
    """Canonicalize a free-text alloy grade, else ``None`` when none is present.

    Нормализация свободной строки марки к канонической форме, иначе ``None``.
    """
    described = describe_grade(surface)
    return described.canonical if described else None


def grade_family(grade: str) -> str | None:
    """Broad alloy family for a grade surface/canonical, else ``None`` if unknown.

    Семейство сплава (aluminium/nickel/titanium/steel) по марке, иначе ``None``.
    """
    described = describe_grade(grade)
    return described.family if described else None
