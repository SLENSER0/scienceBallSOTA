"""§13.16 модель серьёзности нарушений / verifier violation severity model.

The §13.16 verifier must fill ``verifier_report`` with a «список нарушений с
severity» — a list of violations, each tagged with how badly it undermines the
answer. :mod:`agent_service.verifier` produces the raw violation kinds and
:mod:`agent_service.verifier_retry` decides *fixable* routing, but neither
assigns a severity. This module supplies that missing layer.

Each violation is a ``dict`` carrying at least a ``kind``. :func:`classify`
looks the kind up in :data:`RULE_SEVERITY` (unknown kinds default to ``'warn'``,
the safe middle ground), injects a ``severity`` key, then rolls the tagged
violations up into a frozen :class:`SeverityReport`:

* ``max_severity`` — the highest severity present, by :data:`SEVERITY_RANK`
  (``'none'`` when there are no violations);
* ``blocking`` — ``True`` iff any violation is ``'block'``;
* ``counts`` — per-severity tallies that always sum to ``len(violations)``.

Deterministic and dependency-free — see :mod:`agent_service.verifier` for the
graph-backed grounding that produces these violation kinds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Rank of each severity, higher = worse (severity ordering / ранг серьёзности).
SEVERITY_RANK: dict[str, int] = {"block": 3, "warn": 2, "info": 1}

# §13.16 violation kind -> severity / соответствие вида нарушения серьёзности.
RULE_SEVERITY: dict[str, str] = {
    "numeric_claim_without_evidence": "block",
    "unsupported_claim": "block",
    "mixed_units": "warn",
    "entity_substituted": "block",
    "unmarked_contradiction": "warn",
    "low_confidence": "info",
}

# Severity assigned to a violation kind not present in RULE_SEVERITY (по умолчанию).
_DEFAULT_SEVERITY = "warn"

# max_severity value when there are no violations (пустой отчёт).
_NO_SEVERITY = "none"


@dataclass(frozen=True)
class SeverityReport:
    """§13.16 отчёт о серьёзности / rolled-up severity report.

    ``violations`` are the input violations in original order, each with a
    ``severity`` key injected; ``max_severity`` is the worst severity present by
    :data:`SEVERITY_RANK` (``'none'`` when empty); ``blocking`` is ``True`` iff
    any violation is ``'block'``; ``counts`` maps every known severity to how
    many violations carry it (always summing to ``len(violations)``).
    """

    violations: tuple[dict, ...]
    max_severity: str
    blocking: bool
    counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        """Serialise for ``verifier_report`` (JSON-friendly / для сериализации)."""
        return {
            "violations": [dict(v) for v in self.violations],
            "max_severity": self.max_severity,
            "blocking": self.blocking,
            "counts": dict(self.counts),
        }


def severity_for(kind: str) -> str:
    """Severity of a violation ``kind``; unknown kinds -> ``'warn'`` (см. §13.16)."""
    return RULE_SEVERITY.get(kind, _DEFAULT_SEVERITY)


def classify(violations: list[dict]) -> SeverityReport:
    """Tag each violation with a ``severity`` and roll up a :class:`SeverityReport`.

    Every input violation is copied and given a ``severity`` key derived from its
    ``kind`` via :func:`severity_for` (unknown kinds default to ``'warn'``). The
    report's ``max_severity`` is the highest severity present by
    :data:`SEVERITY_RANK` (``'none'`` for empty input), ``blocking`` is ``True``
    iff any violation is ``'block'``, and ``counts`` tallies each known severity.
    """
    counts: dict[str, int] = dict.fromkeys(SEVERITY_RANK, 0)
    tagged: list[dict] = []
    max_rank = 0
    max_severity = _NO_SEVERITY
    blocking = False

    for v in violations:
        item = dict(v)
        severity = severity_for(str(item.get("kind", "")))
        item["severity"] = severity
        tagged.append(item)
        counts[severity] += 1
        rank = SEVERITY_RANK[severity]
        if rank > max_rank:
            max_rank = rank
            max_severity = severity
        if severity == "block":
            blocking = True

    return SeverityReport(
        violations=tuple(tagged),
        max_severity=max_severity,
        blocking=blocking,
        counts=counts,
    )
