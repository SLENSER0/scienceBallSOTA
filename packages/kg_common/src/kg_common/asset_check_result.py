"""Dagster asset-check outcomes for the healthcheck asset — результаты проверок (§9.4).

Dagster's ``@asset_check`` mechanism attaches health probes (e.g. "can we reach
Neo4j?", "is qdrant warm?") to an asset and reports each as an
``AssetCheckResult`` carrying a *passed* flag, a *severity* (``WARN`` or
``ERROR``) and free-form metadata. §9.4 aggregates those outcomes into the
single healthcheck asset's verdict: the system is *ok* iff no check produced a
**blocking** failure — a failed check whose severity is ``ERROR``. A failed
``WARN`` degrades but never blocks; a passing ``ERROR``-severity check is fine.

This module is pure — детерминизм: no I/O, no clock, no Dagster import. It
models one check via the frozen :class:`CheckResult` and folds a sequence of
them with :func:`aggregate`. :func:`blocking` is the single source of truth for
"does this outcome block?" and is reused by :func:`aggregate`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

__all__ = [
    "CheckResult",
    "VALID_SEVERITIES",
    "aggregate",
    "blocking",
]

# The severities a check may carry — допустимые уровни (§9.4). ``ERROR`` on a
# failed check blocks the healthcheck; ``WARN`` only degrades.
VALID_SEVERITIES: frozenset[str] = frozenset({"WARN", "ERROR"})

# Immutable empty default for ``metadata`` — общий неизменяемый пустой маппинг.
_EMPTY_METADATA: Mapping[str, object] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One Dagster asset-check outcome — результат одной проверки (§9.4).

    ``name`` is the check's identifier (non-empty). ``passed`` is its verdict.
    ``severity`` is ``WARN`` or ``ERROR``. ``metadata`` is arbitrary probe
    detail (defaults to an empty immutable mapping). A failed ``ERROR`` check
    is *blocking*; see :func:`blocking`.
    """

    name: str
    passed: bool
    severity: str
    metadata: Mapping[str, object] = field(default=_EMPTY_METADATA)

    def __post_init__(self) -> None:
        """Validate name and severity — валидация имени и уровня (§9.4)."""
        if not self.name or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"severity must be one of {sorted(VALID_SEVERITIES)}, got {self.severity!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict — сериализация в словарь."""
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "metadata": dict(self.metadata),
            "blocking": blocking(self),
        }


def blocking(result: CheckResult) -> bool:
    """True iff a failed ``ERROR`` check — блокирующая ошибка (§9.4).

    A check blocks the healthcheck asset only when it both failed and carries
    ``ERROR`` severity. A passing ``ERROR`` check or any ``WARN`` check never
    blocks.
    """
    return (not result.passed) and result.severity == "ERROR"


def aggregate(results: Sequence[CheckResult]) -> dict[str, Any]:
    """Fold check outcomes into a healthcheck verdict — свод проверок (§9.4).

    Returns a dict with ``total`` (count), ``passed`` (count that passed),
    ``failed`` (count that failed), ``blocking`` (count of blocking failures),
    ``worst_severity`` (``ERROR`` if any check is ``ERROR`` else ``WARN`` if any
    is ``WARN`` else ``None`` when empty) and ``ok`` — true iff no blocking
    failures. An empty sequence is vacuously ``ok``.
    """
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    blocking_count = sum(1 for r in results if blocking(r))
    if any(r.severity == "ERROR" for r in results):
        worst_severity: str | None = "ERROR"
    elif any(r.severity == "WARN" for r in results):
        worst_severity = "WARN"
    else:
        worst_severity = None
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "blocking": blocking_count,
        "worst_severity": worst_severity,
        "ok": blocking_count == 0,
    }
