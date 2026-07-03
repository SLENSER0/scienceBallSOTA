"""Answer-unit correctness metric — точность единиц измерения (§18.8).

Judges whether an answer carries the *right unit*, reusing the physical
dimension arithmetic of :mod:`kg_common.units.conversions`
(:func:`are_compatible` / :func:`convert` / :func:`dimension_of`). Three
independent facets are scored for each ``(expected, actual)`` pair:

* **exact**      — the two unit strings are equal after NFKC folding (the
  answer used the canonical/expected unit verbatim, e.g. ``MPa`` == ``MPa``);
* **compatible** — both units resolve to the *same physical dimension* and are
  therefore inter-convertible (``MPa`` ↔ ``GPa``), even if not identical;
* **mixed**      — the actual unit resolves to a *different* dimension than the
  expected one (``MPa`` vs ``K``): this is the verifier «units not mixed» rule
  (§18.8), a hard error distinct from a mere unit mismatch.

A missing ``actual`` (``None``) is neither exact, compatible, nor mixed — there
is simply no unit to judge, so all three facets are ``False``.

Because the conversions registry (§7.10) is intentionally small, a handful of
policy-allowed pressure symbols it omits (``GPa``, ``N/mm2``, ``kgf/mm2`` — see
:data:`kg_common.units.policy.PROPERTY_UNIT_POLICY`) are resolved through a tiny
supplemental dimension map so ``MPa``/``GPa`` reads as compatible, not mixed.

Pure Python, no I/O. :func:`unit_accuracy` aggregates a list of pairs into
``exact_rate`` / ``compatible_rate`` / ``mixed_rate`` / ``n``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from kg_common.units.conversions import (
    UnknownUnitError,
    are_compatible,
    dimension_of,
)

# Policy-allowed pressure units the §7.10 conversion registry does not list, so
# ``MPa``/``GPa`` judge as compatible (same dimension) rather than mixed (§18.8).
_EXTRA_DIMENSIONS: dict[str, str] = {
    "gpa": "pressure",
    "n/mm2": "pressure",
    "n/mm^2": "pressure",
    "kgf/mm2": "pressure",
    "kgf/mm^2": "pressure",
}


def _normalize(unit: str) -> str:
    """Fold a unit token for exact comparison: NFKC + strip, case-preserved.

    Mirrors :func:`kg_common.units.conversions._normalize` — case is significant
    for units (``MPa`` ≠ ``mPa``), so this deliberately does not lowercase.
    """
    return unicodedata.normalize("NFKC", str(unit)).strip()


def _dimension_of(unit: str | None) -> str | None:
    """Physical dimension of *unit*, or ``None`` if unresolvable (§18.8).

    Tries the §7.10 registry first, then a small supplemental map for
    policy-allowed pressure symbols the registry omits (e.g. ``GPa``).
    """
    if unit is None:
        return None
    try:
        return dimension_of(unit)
    except UnknownUnitError:
        return _EXTRA_DIMENSIONS.get(_normalize(unit).replace("^", "").lower())


@dataclass(frozen=True)
class UnitJudgement:
    """Per-pair verdict on answer-unit correctness — вердикт единицы (§18.8).

    ``exact`` ⇒ normalized-equal strings; ``compatible`` ⇒ same physical
    dimension (inter-convertible); ``mixed`` ⇒ actual dimension differs from
    expected (the verifier «units not mixed» violation). A ``None`` *actual*
    yields all three ``False``.
    """

    expected: str
    actual: str | None
    exact: bool
    compatible: bool
    mixed: bool

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view with stable keys (§18.8)."""
        return {
            "expected": self.expected,
            "actual": self.actual,
            "exact": self.exact,
            "compatible": self.compatible,
            "mixed": self.mixed,
        }


def judge_unit(expected: str, actual: str | None) -> UnitJudgement:
    """Judge one ``actual`` unit against the ``expected`` one (§18.8).

    * ``exact``      — ``actual`` equals ``expected`` after NFKC folding;
    * ``compatible`` — both units share a physical dimension (per
      :func:`kg_common.units.conversions.are_compatible`, extended to a few
      policy-only pressure symbols);
    * ``mixed``      — ``actual`` resolves to a *different* dimension than
      ``expected`` (verifier «units not mixed» rule).

    A ``None`` ``actual`` is not judged: ``exact``/``compatible``/``mixed`` are
    all ``False``.
    """
    if actual is None:
        return UnitJudgement(expected, None, exact=False, compatible=False, mixed=False)

    exact = _normalize(expected) == _normalize(actual)

    exp_dim = _dimension_of(expected)
    act_dim = _dimension_of(actual)
    both_known = exp_dim is not None and act_dim is not None

    compatible = exact or are_compatible(expected, actual) or (both_known and exp_dim == act_dim)
    mixed = both_known and exp_dim != act_dim

    return UnitJudgement(expected, actual, exact=exact, compatible=compatible, mixed=mixed)


def unit_accuracy(pairs: list[tuple[str, str | None]]) -> dict:
    """Aggregate unit judgements over ``(expected, actual)`` *pairs* (§18.8).

    Returns ``exact_rate`` / ``compatible_rate`` / ``mixed_rate`` — the fraction
    of pairs that are exact, compatible, and mixed respectively — plus ``n`` (the
    number of pairs judged). An empty list yields all-zero rates and ``n == 0``.
    """
    n = len(pairs)
    if n == 0:
        return {"exact_rate": 0.0, "compatible_rate": 0.0, "mixed_rate": 0.0, "n": 0}

    judged = [judge_unit(expected, actual) for expected, actual in pairs]
    exact = sum(1 for j in judged if j.exact)
    compatible = sum(1 for j in judged if j.compatible)
    mixed = sum(1 for j in judged if j.mixed)
    return {
        "exact_rate": exact / n,
        "compatible_rate": compatible / n,
        "mixed_rate": mixed / n,
        "n": n,
    }
