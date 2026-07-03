"""Categorized prompt-injection scanner (§19.6 guardrails).

``cypher_guard.is_prompt_injection`` returns a bare bool and
``sanitize.detect_injection`` returns a flat list — neither tells you *what kind*
of injection was attempted nor how risky the text is. This module adds a
categorized, scored risk report on top of the same idea.

Каждый подозрительный фрагмент относится к одной из категорий
(«instruction_override», «data_exfiltration», «tool_policy», «graph_mutation»),
получает :class:`InjectionHit` со своим span, а :func:`scan` собирает их в
:class:`InjectionReport` с оценкой риска и уровнем серьёзности.

The scan is case-insensitive, pure-python/regex, and never mutates its input.
Overlapping matches are de-duplicated so a longer pattern is not double-counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Category names — kept as module constants so callers can reference them.
INSTRUCTION_OVERRIDE = "instruction_override"
DATA_EXFILTRATION = "data_exfiltration"
TOOL_POLICY = "tool_policy"
GRAPH_MUTATION = "graph_mutation"

# Per-category signature patterns. Each regex is compiled case-insensitively and
# matched against the raw text; the matched substring becomes the hit's pattern.
_SIGNATURES: dict[str, tuple[re.Pattern[str], ...]] = {
    INSTRUCTION_OVERRIDE: (
        re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)", re.IGNORECASE),
        re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|above)", re.IGNORECASE),
        re.compile(r"forget\s+(?:everything|all|previous|prior)", re.IGNORECASE),
        re.compile(r"override\s+(?:the\s+)?(?:system|instructions?|prompt)", re.IGNORECASE),
        re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    ),
    DATA_EXFILTRATION: (
        re.compile(r"reveal\b", re.IGNORECASE),
        re.compile(r"exfiltrat\w*", re.IGNORECASE),
        re.compile(r"\bleak\b", re.IGNORECASE),
        re.compile(r"dump\s+(?:the\s+)?(?:data|graph|db|database)", re.IGNORECASE),
        re.compile(r"send\s+(?:the\s+|all\s+)?\w*\s*data\b", re.IGNORECASE),
    ),
    TOOL_POLICY: (
        re.compile(r"disable\s+(?:the\s+)?(?:tool|guard|filter|policy)", re.IGNORECASE),
        re.compile(r"bypass\s+(?:the\s+)?(?:tool|guard|filter|policy|check)", re.IGNORECASE),
        re.compile(r"without\s+(?:any\s+)?(?:restriction|limit|guard)", re.IGNORECASE),
        re.compile(r"call\s+(?:the\s+)?admin\s+tool", re.IGNORECASE),
    ),
    GRAPH_MUTATION: (
        re.compile(r"\bdetach\s+delete\b", re.IGNORECASE),
        re.compile(r"\bdelete\b", re.IGNORECASE),
        re.compile(r"\bdrop\b", re.IGNORECASE),
        re.compile(r"\bmerge\b", re.IGNORECASE),
        re.compile(r"\bremove\b", re.IGNORECASE),
        re.compile(r"\btruncate\b", re.IGNORECASE),
    ),
}

# Severity band thresholds on the [0, 1] risk score («уровни серьёзности»).
_MEDIUM_THRESHOLD = 0.5
_HIGH_THRESHOLD = 0.75


@dataclass(frozen=True)
class InjectionHit:
    """A single matched injection signature («сигнатура инъекции»)."""

    category: str
    pattern: str
    span: tuple[int, int]

    def as_dict(self) -> dict[str, Any]:
        """Serialise the hit to a plain dict (roundtrips via ``InjectionHit(**d)``)."""
        return {"category": self.category, "pattern": self.pattern, "span": self.span}


@dataclass(frozen=True)
class InjectionReport:
    """Scored, categorized injection risk report («отчёт о риске инъекции»)."""

    hits: tuple[InjectionHit, ...]
    score: float
    severity: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise the report and its hits to a JSON-friendly dict."""
        return {
            "hits": tuple(hit.as_dict() for hit in self.hits),
            "score": self.score,
            "severity": self.severity,
        }


def _severity_band(score: float) -> str:
    """Map a risk *score* onto a ``none/low/medium/high`` band (§19.6)."""
    if score <= 0.0:
        return "none"
    if score < _MEDIUM_THRESHOLD:
        return "low"
    if score < _HIGH_THRESHOLD:
        return "medium"
    return "high"


def _collect_hits(text: str) -> list[InjectionHit]:
    """Gather non-overlapping signature hits across every category, in text order."""
    raw: list[InjectionHit] = []
    for category, patterns in _SIGNATURES.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                raw.append(
                    InjectionHit(
                        category=category,
                        pattern=match.group(0).lower(),
                        span=match.span(),
                    )
                )
    raw.sort(key=lambda hit: (hit.span[0], -(hit.span[1] - hit.span[0])))
    accepted: list[InjectionHit] = []
    last_end = -1
    for hit in raw:
        if hit.span[0] >= last_end:  # skip spans overlapping an already-taken hit
            accepted.append(hit)
            last_end = hit.span[1]
    return accepted


def scan(text: str) -> InjectionReport:
    """Scan *text* for prompt-injection signatures and score the risk (§19.6).

    Score is ``min(1.0, len(hits) * 0.34)``; severity is banded
    ``none`` (0) / ``low`` (<0.5) / ``medium`` (<0.75) / ``high``.
    """
    hits = tuple(_collect_hits(text))
    score = min(1.0, len(hits) * 0.34)
    return InjectionReport(hits=hits, score=score, severity=_severity_band(score))


def is_high_risk(report: InjectionReport, threshold: float = 0.5) -> bool:
    """True if *report*'s score meets or exceeds *threshold* («высокий риск»)."""
    return report.score >= threshold
