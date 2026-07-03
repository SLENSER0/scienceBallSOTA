"""GraphRAG mode guard (§11.12).

Решает, каким режимом отвечать на запрос — GraphRAG (обзор на основе community
summaries) или гибридным (vector + BM25 + graph) поиском. GraphRAG становится
*primary* только на «all-clear» пути: фича включена, есть активный build
(``build_status == 'built'``) и запрос имеет глобальный (обзорный) интент. В любом
другом случае режим — ``'hybrid'`` с ``fallback='hybrid'`` и предупреждением о
причине.

The guard is pure logic: it takes already-computed inputs (feature flag, build
status string, global-intent verdict) and returns a frozen :class:`ModeDecision`.
It never touches the graph or the network. A narrow/numeric query
(``is_global_intent`` ``False``) is never routed to GraphRAG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Валидные режимы ответа (§11.12).
_MODE_GRAPHRAG = "graphrag"
_MODE_HYBRID = "hybrid"

# Build-status value that marks an active, usable GraphRAG build (§11.12).
_BUILT = "built"

# Reason codes — machine-readable выжимка причины решения.
_REASON_PRIMARY = "graphrag primary: enabled + global intent + active build"
_REASON_DISABLED = "graphrag disabled"
_REASON_NO_BUILD = "no active build"
_REASON_BUILD_FAILED = "build failed"
_REASON_NOT_GLOBAL = "narrow/numeric intent"

# Warning messages surfaced to the caller on each declined path.
_WARN_DISABLED = "GraphRAG disabled; falling back to hybrid retrieval"
_WARN_NO_BUILD = "no active GraphRAG build; falling back to hybrid retrieval"
_WARN_BUILD_FAILED = "GraphRAG build failed; falling back to hybrid retrieval"

# Units that mark a numeric material-property clause (§11.12 structured shape).
_UNITS = (
    r"MPa|GPa|kPa|Pa|N|kN|"
    r"°C|K|"
    r"%|wt\.?%|at\.?%|vol\.?%|"
    r"mm|cm|μm|um|nm|m|"
    r"HV|HRC|HB|"
    r"MPa√m|MPa\.m|"
    r"s|h|min|"
    r"g/cm3|kg/m3"
)

# «число + единица» — e.g. ``320 MPa``, ``12.5%``, ``550°C``.
_NUMERIC_UNIT_RE = re.compile(
    rf"(?<![\w.])\d+(?:[.,]\d+)?\s*(?:{_UNITS})(?![\w])",
    re.IGNORECASE,
)

# Property keywords (EN/RU) that anchor a material-regime-property query.
_PROPERTY_TERMS = (
    "hardness",
    "strength",
    "yield",
    "modulus",
    "toughness",
    "ductility",
    "conductivity",
    "density",
    "твёрдость",
    "твердость",
    "прочность",
    "модуль",
    "вязкость",
    "плотность",
)


@dataclass(frozen=True)
class ModeDecision:
    """Outcome of the GraphRAG mode guard (§11.12).

    ``mode`` is one of ``{'graphrag', 'hybrid'}``. On the all-clear path ``mode`` is
    ``'graphrag'``, ``primary`` is ``True``, ``fallback`` and ``warning`` are
    ``None``. On any declined path ``mode`` is ``'hybrid'``, ``primary`` is
    ``False``, ``fallback`` is ``'hybrid'`` and ``warning`` states the cause.
    ``reason`` is a short machine-readable code echoing the decision.
    """

    mode: str
    primary: bool
    fallback: str | None
    warning: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{mode, primary, fallback, warning, reason}``."""
        return {
            "mode": self.mode,
            "primary": self.primary,
            "fallback": self.fallback,
            "warning": self.warning,
            "reason": self.reason,
        }


def is_structured_query(query: str) -> bool:
    """Detect a material-regime-property / numeric query shape (§11.12).

    Returns ``True`` when the query carries a numeric-with-unit clause (e.g.
    ``320 MPa``, ``12.5%``, ``550°C``) or pairs a material-property keyword with a
    number. Broad survey questions (``'общий обзор темы'``) return ``False``. Such
    structured/numeric queries are narrow by nature and must never route to
    GraphRAG.
    """
    if not query:
        return False
    text = query.strip()
    if _NUMERIC_UNIT_RE.search(text):
        return True
    lowered = text.lower()
    has_number = re.search(r"(?<![\w.])\d+(?:[.,]\d+)?", lowered) is not None
    has_property = any(term in lowered for term in _PROPERTY_TERMS)
    return has_number and has_property


def decide_mode(
    query: str,
    *,
    enabled: bool,
    build_status: str | None,
    is_global_intent: bool,
) -> ModeDecision:
    """Decide the retrieval mode for a query (§11.12).

    GraphRAG becomes *primary* (``mode='graphrag'``, ``primary=True``, ``warning``
    ``None``) iff all three hold: ``enabled`` is set, ``is_global_intent`` is set,
    and an active build exists (``build_status == 'built'``).

    Otherwise ``mode='hybrid'`` with ``primary=False``, ``fallback='hybrid'`` and a
    ``warning`` naming the first blocking cause, checked in order: feature off, then
    build failed (``build_status == 'failed'``), then no active build (any other
    non-``'built'`` status, including ``None``), then a narrow/numeric query
    (``is_global_intent`` ``False``, or a structured query per
    :func:`is_structured_query`). A narrow/numeric query is therefore never routed
    to GraphRAG even when the feature is enabled and a build exists.
    """
    narrow = (not is_global_intent) or is_structured_query(query)

    if not enabled:
        return _hybrid(_WARN_DISABLED, _REASON_DISABLED)
    if build_status == "failed":
        return _hybrid(_WARN_BUILD_FAILED, _REASON_BUILD_FAILED)
    if build_status != _BUILT:
        return _hybrid(_WARN_NO_BUILD, _REASON_NO_BUILD)
    if narrow:
        return _hybrid(None, _REASON_NOT_GLOBAL)
    return ModeDecision(_MODE_GRAPHRAG, True, None, None, _REASON_PRIMARY)


def _hybrid(warning: str | None, reason: str) -> ModeDecision:
    """Build a declined (hybrid) decision with the given warning and reason."""
    return ModeDecision(_MODE_HYBRID, False, _MODE_HYBRID, warning, reason)
