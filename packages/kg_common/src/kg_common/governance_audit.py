"""Governance compliance audit — аудит соответствия управлению данными (§10.11).

Finds datasets that are missing required *governance* metadata: a subject
``domain`` and the two mandatory governance-tag facets ``access`` and
``quality``. This is deliberately **distinct** from ``ownership_audit`` (which
checks ``owner`` / ``lab``): here we care only about the governance surface
described in §10.11 — домен, класс доступа, состояние качества.

A dataset is a plain :class:`~collections.abc.Mapping` with keys:

* ``id``     — dataset identifier (идентификатор набора данных).
* ``domain`` — subject-domain string; *falsy* (``""`` / ``None`` / missing)
  counts as missing (домен отсутствует).
* ``tags``   — list of ``"facet:value"`` strings (список тегов ``facet:value``).

A dataset *violates* when any of the following hold, in this fixed order:

1. ``domain`` is falsy                          → ``"domain"``.
2. no tag has facet ``access`` (``access:*``)   → ``"access"``.
3. no tag has facet ``quality`` (``quality:*``) → ``"quality"``.

The resulting ``missing`` tuple is always an *ordered subset* of
``("domain", "access", "quality")``.

Pure and deterministic — no store, no I/O, no wall-clock. Everything is a frozen
dataclass, so results cannot be mutated after construction.

Public API:

* :class:`GovernanceViolation` — frozen ``{dataset_id, missing}`` record.
* :class:`GovernanceReport`     — frozen aggregate over an audit run.
* :func:`audit_governance`      — audit an iterable of datasets → report.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "REQUIRED_FACETS",
    "GOVERNANCE_FIELDS",
    "GovernanceViolation",
    "GovernanceReport",
    "audit_governance",
]

# -- required governance-tag facets (обязательные фасеты тегов) --------------
FACET_ACCESS = "access"
FACET_QUALITY = "quality"

#: Governance-tag facets that must be present on every dataset (§10.11).
REQUIRED_FACETS: tuple[str, ...] = (FACET_ACCESS, FACET_QUALITY)

#: Canonical order of the governance fields reported in ``missing``.
GOVERNANCE_FIELDS: tuple[str, ...] = ("domain", "access", "quality")


@dataclass(frozen=True)
class GovernanceViolation:
    """One dataset missing governance metadata — нарушение по одному набору.

    :param dataset_id: identifier of the offending dataset (идентификатор).
    :param missing: ordered subset of :data:`GOVERNANCE_FIELDS` that is absent.
    """

    dataset_id: str
    missing: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-friendly dict — сериализация в словарь."""
        return {"dataset_id": self.dataset_id, "missing": list(self.missing)}


@dataclass(frozen=True)
class GovernanceReport:
    """Aggregate result of a governance audit — итог аудита управления.

    :param violations: all violating datasets, in input order (нарушения).
    :param checked: number of datasets inspected (сколько проверено).
    """

    violations: tuple[GovernanceViolation, ...]
    checked: int

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-friendly dict — сериализация в словарь."""
        return {
            "violations": [v.as_dict() for v in self.violations],
            "checked": self.checked,
            "violation_count": self.violation_count(),
            "clean": self.is_clean(),
        }

    def is_clean(self) -> bool:
        """``True`` when no dataset violated — нет нарушений."""
        return not self.violations

    def violation_count(self) -> int:
        """Number of violating datasets — число нарушивших наборов."""
        return len(self.violations)


def _has_facet(tags: Any, facet: str) -> bool:
    """Does any ``tag`` in ``tags`` carry ``facet:`` prefix? — есть ли фасет."""
    if not isinstance(tags, Iterable) or isinstance(tags, (str, bytes)):
        return False
    prefix = f"{facet}:"
    return any(isinstance(t, str) and t.startswith(prefix) for t in tags)


def _dataset_missing(dataset: Mapping[str, Any]) -> tuple[str, ...]:
    """Compute the ordered ``missing`` tuple for one dataset — что отсутствует."""
    tags = dataset.get("tags")
    missing: list[str] = []
    if not dataset.get("domain"):
        missing.append("domain")
    if not _has_facet(tags, FACET_ACCESS):
        missing.append("access")
    if not _has_facet(tags, FACET_QUALITY):
        missing.append("quality")
    return tuple(missing)


def audit_governance(datasets: Iterable[Mapping[str, Any]]) -> GovernanceReport:
    """Audit ``datasets`` for missing governance metadata — провести аудит.

    Each dataset is inspected in order; a :class:`GovernanceViolation` is emitted
    for every dataset with a non-empty ``missing`` tuple. ``checked`` equals the
    total number of datasets seen (включая безупречные).

    :param datasets: iterable of mappings with ``id`` / ``domain`` / ``tags``.
    :returns: an immutable :class:`GovernanceReport`.
    """
    violations: list[GovernanceViolation] = []
    checked = 0
    for dataset in datasets:
        checked += 1
        missing = _dataset_missing(dataset)
        if missing:
            violations.append(
                GovernanceViolation(dataset_id=str(dataset.get("id", "")), missing=missing)
            )
    return GovernanceReport(violations=tuple(violations), checked=checked)
