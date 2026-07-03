"""Comparison invariants — never compare across incompatible property/unit (§24.13).

Инварианты сравнимости: two measurement rows may only be compared when they
describe **the same property** *and* carry **compatible units**. The audit
(§24.13) found comparison tables that lined up, e.g., a hardness reading (HV)
against a strength reading (MPa), or MPa against a dimensionless ratio — an
apples-to-oranges error that silently produces nonsense "winners".

This module is a pure-python guard rail (no graph, no I/O). It reuses
:func:`kg_extractors.units.to_canonical` so that unit compatibility is judged on
the *canonical* unit, not the raw token: ``MPa`` and Cyrillic ``МПа`` both
canonicalise to ``bar`` and are therefore comparable, whereas ``HV`` (unknown to
the registry) and ``MPa`` are not.

Three entry points:

- :func:`check_comparable` — the predicate, returning a frozen
  :class:`ComparabilityResult` with a human-readable ``reason``;
- :func:`enforce_invariants` — sweeps a list of rows, grouping by ``property_id``
  and flagging any *same-property* pair whose units are incompatible (a genuine
  data error; cross-property pairs are simply kept apart, not flagged);
- :func:`safe_compare` — a guarded three-way compare that raises
  :class:`ComparisonError` rather than return a meaningless ordering.

Rows are plain dicts: ``{"property_id": str, "unit": str | None, "value": ...}``.
Only ``property_id`` and ``unit`` gate comparability; ``value`` is read by
:func:`safe_compare` when present.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass

from kg_extractors.units import to_canonical

# Reason codes (stable substrings tests / callers can match on).
REASON_OK = "comparable: same property_id and compatible unit"
REASON_MISSING_PROPERTY = "not comparable: missing property_id on one or both rows"


class ComparisonError(ValueError):
    """Raised by :func:`safe_compare` when two rows must not be compared (§24.13)."""


@dataclass(frozen=True)
class ComparabilityResult:
    """Verdict for a single row pair (§24.13).

    ``comparable`` is the predicate; ``reason`` is a human-readable RU/EN-friendly
    explanation (стабильная строка) usable in reports and assertions.
    """

    comparable: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InvariantViolation:
    """One flagged pair from :func:`enforce_invariants` (§24.13).

    ``i``/``j`` are the row indices (i < j) into the input list; ``property_id`` is
    the shared property whose measurements clashed; ``reason`` explains why.
    """

    i: int
    j: int
    property_id: str
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def _property_id(row: dict) -> str | None:
    """Return the row's ``property_id`` (None when absent, empty or null)."""
    pid = row.get("property_id")
    if pid is None:
        return None
    pid = str(pid).strip()
    return pid or None


def _unit_key(unit: str | None) -> tuple[str, str | None]:
    """Map a raw unit token to a comparison key so equal keys == compatible units.

    - missing / blank unit -> ``("none", None)`` (dimensionless, compatible only
      with another missing unit);
    - a unit the registry knows -> ``("canonical", <canonical unit>)`` so ``MPa``
      and ``МПа`` collapse to the same ``("canonical", "bar")``;
    - a unit unknown to the registry (e.g. ``HV``) -> ``("raw", <nfkc-lower>)`` so
      identical unknown tokens still match but never a known, dimensioned unit.
    """
    if unit is None or not str(unit).strip():
        return ("none", None)
    norm = to_canonical(1.0, unit)
    if norm is not None:
        return ("canonical", norm.unit)
    return ("raw", unicodedata.normalize("NFKC", str(unit)).strip().lower())


def check_comparable(a: dict, b: dict) -> ComparabilityResult:
    """Judge whether rows ``a`` and ``b`` may be compared (§24.13).

    Requires (1) both rows to carry the **same** non-empty ``property_id`` and
    (2) **compatible** units (same canonical unit, per :func:`_unit_key`). Property
    identity is checked first, so a property mismatch is reported as such even when
    the units also differ.
    """
    pa, pb = _property_id(a), _property_id(b)
    if pa is None or pb is None:
        return ComparabilityResult(False, REASON_MISSING_PROPERTY)
    if pa != pb:
        return ComparabilityResult(False, f"not comparable: different property_id {pa!r} != {pb!r}")
    ua, ub = _unit_key(a.get("unit")), _unit_key(b.get("unit"))
    if ua != ub:
        return ComparabilityResult(
            False,
            f"not comparable: incompatible units {a.get('unit')!r} vs {b.get('unit')!r}",
        )
    return ComparabilityResult(True, REASON_OK)


def enforce_invariants(rows: list[dict]) -> list[InvariantViolation]:
    """Flag every same-property pair whose units are incompatible (§24.13).

    Rows are grouped by ``property_id``; comparing across *different* properties is
    not a violation (the invariant simply keeps those apart), but two rows of the
    **same** property in incompatible units is a data error worth surfacing. Rows
    without a ``property_id`` are skipped (nothing to enforce against).

    Returns the violations ordered by ``(i, j)``.
    """
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        pid = _property_id(row)
        if pid is not None:
            groups.setdefault(pid, []).append(idx)
    violations: list[InvariantViolation] = []
    for pid, idxs in groups.items():
        for a_pos in range(len(idxs)):
            for b_pos in range(a_pos + 1, len(idxs)):
                i, j = idxs[a_pos], idxs[b_pos]
                res = check_comparable(rows[i], rows[j])
                if not res.comparable:
                    violations.append(InvariantViolation(i, j, pid, res.reason))
    violations.sort(key=lambda v: (v.i, v.j))
    return violations


def _canonical_value(row: dict) -> float | None:
    """Return the row's ``value`` in canonical units (None if not numeric/known)."""
    if "value" not in row or row["value"] is None:
        return None
    try:
        value = float(row["value"])
    except (TypeError, ValueError):
        return None
    norm = to_canonical(value, row.get("unit"))
    return norm.value if norm is not None else value


def safe_compare(a: dict, b: dict) -> int:
    """Three-way compare of two rows in canonical units, guarding the invariant.

    Returns the sign of ``a.value - b.value`` (-1 / 0 / 1) once both values are
    canonicalised, so ``1 MPa`` (== 10 bar) compares greater than ``5 bar``. Raises
    :class:`ComparisonError` (carrying the ``reason``) when the rows are not
    comparable; returns ``0`` when either value is missing/non-numeric.
    """
    res = check_comparable(a, b)
    if not res.comparable:
        raise ComparisonError(res.reason)
    va, vb = _canonical_value(a), _canonical_value(b)
    if va is None or vb is None:
        return 0
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0
