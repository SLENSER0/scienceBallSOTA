"""Unit/value problem classification + curator review flags (§7.6).

Folds the property-unit policy (§7.2 / §7.7, :mod:`kg_common.units.policy`) and
the unit normalizer (§7, :mod:`kg_extractors.units`) into a single *problem
report* for one extracted ``value`` + ``unit`` pair. Where
:mod:`kg_extractors.measurement_normalizer` (§7.5) produces a normalized
measurement, this module diagnoses *what is wrong* with it and whether a human
must look.

Detected problems (проблемы значения/единицы):

* ``missing_unit`` — a value with no unit where one is expected (нет единицы) —
  raises the ``is_missing_unit_gap`` signal for the gap-analysis pipeline;
* ``unparseable_unit`` — a present unit that is neither policy-allowed nor
  pint-parseable (нераспознанная единица) → severity ``error``;
* ``out_of_range`` — value outside the property's physical/typical bounds
  (вне диапазона, §7.7) → severity ``warning`` (outlier) or ``error`` (hard);
* ``dimensionless_expected_but_unit_present`` — a unit attached to a unitless
  property such as pH (единица у безразмерной величины) → ``warning``;
* ``negative_where_nonneg`` — a negative value for a non-negative-by-definition
  property (отрицательное значение) → ``error``.

The classifier is graceful about unknown properties: when ``property_id`` names
no policy it can only judge unit-shape problems (missing / unparseable), never
range. Pure Python — no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.units.policy import (
    PROPERTY_UNIT_POLICY,
    allowed_units,
    is_unit_allowed,
    validate_range,
)
from kg_extractors.units import to_canonical

# --- problem tokens (проблемы), §7.6 -----------------------------------------
PROBLEM_MISSING_UNIT = "missing_unit"  # нет единицы
PROBLEM_UNPARSEABLE_UNIT = "unparseable_unit"  # нераспознанная единица
PROBLEM_OUT_OF_RANGE = "out_of_range"  # вне диапазона (§7.7)
PROBLEM_DIMENSIONLESS_UNIT = "dimensionless_expected_but_unit_present"  # безразмерная
PROBLEM_NEGATIVE = "negative_where_nonneg"  # отрицательное значение

# --- severity ladder (уровень серьёзности): ok < warning < error -------------
SEVERITY_OK = "ok"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
#: Severity tokens in ascending order — ``SEVERITY_LEVELS.index(sev)`` ranks them.
SEVERITY_LEVELS: tuple[str, str, str] = (SEVERITY_OK, SEVERITY_WARNING, SEVERITY_ERROR)
_RANK: dict[str, int] = {sev: i for i, sev in enumerate(SEVERITY_LEVELS)}

#: Review-task kind emitted for every unit/value problem (§7.6).
REVIEW_TASK_KIND = "unit_problem"


@dataclass(frozen=True)
class ProblemReport:
    """Classification of one ``value``/``unit`` pair (§7.6).

    Fields
    ------
    problems
        Ordered list of problem tokens (``missing_unit`` …); empty ⇒ clean.
    severity
        Highest severity across ``problems`` — ``"ok"`` / ``"warning"`` /
        ``"error"`` (наивысшая серьёзность).
    review_task
        A curator review task dict when any problem was found, else ``None``.
    is_missing_unit_gap
        ``True`` iff the value is present but its (expected) unit is absent —
        the gap signal consumed by the gap-analysis pipeline (§7.6).
    """

    problems: list[str]
    severity: str
    review_task: dict[str, object] | None
    is_missing_unit_gap: bool

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "problems": list(self.problems),
            "severity": self.severity,
            "review_task": self.review_task,
            "is_missing_unit_gap": self.is_missing_unit_gap,
        }


def _to_float(value: object) -> float | None:
    """Coerce *value* to ``float`` (comma decimals allowed); ``None`` on failure."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _unit_missing(unit: str | None) -> bool:
    """True iff *unit* carries no token (нет единицы): ``None`` / blank."""
    return unit is None or not str(unit).strip()


def _make_review_task(
    problems: list[str],
    property_id: str | None,
    value: object,
    unit: str | None,
) -> dict[str, object]:
    """Build the curator review task for the found *problems* (§7.6)."""
    return {
        "kind": REVIEW_TASK_KIND,
        "reason": ", ".join(problems),
        "property_id": property_id,
        "value": value,
        "unit": unit,
    }


def classify_problems(
    value: object,
    unit: str | None,
    *,
    property_id: str | None = None,
) -> ProblemReport:
    """Classify unit/value problems for one measurement (§7.6).

    Diagnoses missing / unparseable units, out-of-range and negative values,
    and units attached to dimensionless properties, then packages a curator
    ``review_task`` (dict ``{kind, reason, property_id, value, unit}``) and the
    ``is_missing_unit_gap`` signal. Bounds and unit policy come from
    :data:`kg_common.units.policy.PROPERTY_UNIT_POLICY`; unit parseability from
    :func:`kg_extractors.units.to_canonical`.
    """
    numeric = _to_float(value)
    missing = _unit_missing(unit)
    unit_str = None if missing else str(unit)
    known = property_id is not None and property_id in PROPERTY_UNIT_POLICY
    unit_allowed = known and is_unit_allowed(property_id, unit)

    problems: list[str] = []
    severity = SEVERITY_OK
    is_missing_unit_gap = False

    def _raise(sev: str) -> None:
        nonlocal severity
        if _RANK[sev] > _RANK[severity]:
            severity = sev

    # Probe unit parseability + canonical value (only when there is a value).
    norm = None
    if not missing and numeric is not None:
        norm = to_canonical(numeric, unit_str)

    # 1. missing_unit — value present, unit absent, and a unit is expected.
    #    A unitless property (e.g. pH) legitimately accepts "no unit".
    if missing and numeric is not None and not unit_allowed:
        problems.append(PROBLEM_MISSING_UNIT)
        is_missing_unit_gap = True
        _raise(SEVERITY_WARNING)

    # 2. dimensionless_expected_but_unit_present — unit on a unitless property.
    dimensionless = not missing and known and not allowed_units(property_id) and not unit_allowed
    if dimensionless:
        problems.append(PROBLEM_DIMENSIONLESS_UNIT)
        _raise(SEVERITY_WARNING)

    # 3. unparseable_unit — a present unit neither policy-allowed nor parseable.
    unit_present = not missing and numeric is not None
    if unit_present and not unit_allowed and norm is None and not dimensionless:
        problems.append(PROBLEM_UNPARSEABLE_UNIT)
        _raise(SEVERITY_ERROR)

    # 4. negative_where_nonneg — negative value for a non-negative property.
    if numeric is not None and known and numeric < 0:
        lo = PROPERTY_UNIT_POLICY[property_id].get("min")
        if lo is not None and float(lo) >= 0:  # type: ignore[arg-type]
            problems.append(PROBLEM_NEGATIVE)
            _raise(SEVERITY_ERROR)

    # 5. out_of_range — physical/typical bounds (§7.7). Only trust the range
    #    check when the unit is acceptable, else the number's scale is unknown.
    unit_trustworthy = unit_allowed or norm is not None
    if numeric is not None and known and unit_trustworthy:
        range_value = norm.value if norm is not None else numeric
        result = validate_range(property_id, range_value)
        if result.severity == SEVERITY_ERROR:
            problems.append(PROBLEM_OUT_OF_RANGE)
            _raise(SEVERITY_ERROR)
        elif result.severity == SEVERITY_WARNING:
            problems.append(PROBLEM_OUT_OF_RANGE)
            _raise(SEVERITY_WARNING)

    review_task = None
    if problems:
        review_task = _make_review_task(problems, property_id, value, unit)

    return ProblemReport(
        problems=problems,
        severity=severity,
        review_task=review_task,
        is_missing_unit_gap=is_missing_unit_gap,
    )
