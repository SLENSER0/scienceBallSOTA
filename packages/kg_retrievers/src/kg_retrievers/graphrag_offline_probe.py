"""GraphRAG offline capability probe (§11.14).

GraphRAG (community-summary retrieval, "Mode C") is an *optional* enhancement.
The four retrieval modes are независимы (independent): Modes A (vector), B
(keyword) and D (graph traversal) must keep working even when Mode C is
unavailable — package missing, no active build, or the feature flag off.

This module makes that guarantee checkable offline. :func:`probe_capability`
takes three already-computed prerequisites and reports a frozen
:class:`GraphRagCapability`: whether GraphRAG is available, which prerequisites
are missing, and — always — the still-functional degraded modes. It is pure
logic: no graph, no network, no import of the optional ``graphrag`` package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Modes that stay functional регардлесс (regardless) of GraphRAG (§11.14).
# A = vector, B = keyword, D = graph traversal. Mode C (GraphRAG) is optional.
_INDEPENDENT_MODES: tuple[str, ...] = ("A", "B", "D")

# Reason strings, one per missing prerequisite (§11.14).
_REASON_NO_PACKAGE = "graphrag package missing"
_REASON_NO_BUILD = "no active graphrag build"
_REASON_FLAG_DISABLED = "graphrag feature flag disabled"


@dataclass(frozen=True)
class GraphRagCapability:
    """Outcome of the offline GraphRAG probe (§11.14).

    ``available`` is ``True`` only when every prerequisite holds. ``reasons``
    lists the missing prerequisites (empty when available). ``degraded_modes``
    always names the still-functional independent modes — proof that Mode C is
    optional — even when ``available`` is ``False``.
    """

    available: bool
    has_active_build: bool
    reasons: list[str]
    degraded_modes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{available, has_active_build, reasons, degraded_modes}``."""
        return {
            "available": self.available,
            "has_active_build": self.has_active_build,
            "reasons": list(self.reasons),
            "degraded_modes": list(self.degraded_modes),
        }


def probe_capability(
    *,
    package_present: bool,
    active_build: dict[str, Any] | None,
    flag_enabled: bool,
) -> GraphRagCapability:
    """Report GraphRAG capability from its three prerequisites (§11.14).

    ``available`` is ``True`` iff ``package_present`` and ``flag_enabled`` and
    ``active_build is not None``. Each failing prerequisite adds a reason. The
    independent modes A/B/D are always reported as degraded (still-functional)
    modes, asserting that Mode C is optional.
    """
    reasons: list[str] = []
    if not package_present:
        reasons.append(_REASON_NO_PACKAGE)
    has_active_build = active_build is not None
    if not has_active_build:
        reasons.append(_REASON_NO_BUILD)
    if not flag_enabled:
        reasons.append(_REASON_FLAG_DISABLED)

    available = package_present and has_active_build and flag_enabled
    return GraphRagCapability(
        available=available,
        has_active_build=has_active_build,
        reasons=reasons,
        degraded_modes=_INDEPENDENT_MODES,
    )


def assert_modes_independent(capability: GraphRagCapability) -> bool:
    """Return ``True`` iff modes A/B/D are all still functional (§11.14).

    Holds regardless of ``capability.available`` — that is the independence
    guarantee: Modes A, B and D never depend on GraphRAG (Mode C).
    """
    return set(_INDEPENDENT_MODES).issubset(set(capability.degraded_modes))
