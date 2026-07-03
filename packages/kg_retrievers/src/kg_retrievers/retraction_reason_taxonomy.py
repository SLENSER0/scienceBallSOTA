"""Retraction reason taxonomy — таксономия причин ретракции (§25.12).

Where :mod:`kg_retrievers.retraction_report` gives a per-observation summary and
:mod:`kg_retrievers.retraction_impact` measures evidence collapse, this module
answers a different question: *what kinds of reasons drive retractions, and which
one dominates?* Free-text retraction reasons (причина ретракции) are noisy, so we
first normalize each into a small set of canonical codes via
:func:`canonical_reason`, then aggregate those codes into buckets with counts,
shares and example strings via :func:`build_taxonomy`.

Records are plain dicts ``{"reason": str, "retracted_by": str, "retracted_at": str}``.
Pure Python and read-only: it reads no store and writes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Canonical codes and the keyword substrings that map free text onto them.
# Ordered: the first code whose any keyword is a substring of the lower-cased
# reason wins (порядок задаёт приоритет при совпадениях).
_REASON_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("superseded", ("supersed", "replaced by", "newer version", " v2", "obsolete")),
    ("error", ("error", "mistake", "incorrect", "wrong", "flaw", "invalid")),
    ("duplicate", ("duplicate", "dupe", "already published", "redundant")),
    ("withdrawn", ("withdraw", "retracted by author", "author request", "voluntary")),
)

# Fallback code when no keyword matches (причина не классифицирована).
OTHER = "other"


@dataclass(frozen=True)
class ReasonBucket:
    """One canonical reason code with its count, share and example reason strings.

    ``share`` is ``count / total`` of the parent taxonomy; ``examples`` holds up to
    ``max_examples`` of the original free-text reasons that mapped onto ``code``.
    """

    code: str
    count: int
    share: float
    examples: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "count": self.count,
            "share": self.share,
            "examples": list(self.examples),
        }


@dataclass(frozen=True)
class ReasonTaxonomy:
    """Aggregated reason buckets over a record set (§25.12).

    ``buckets`` are sorted descending by ``count``; ``total`` is the number of
    records; ``dominant_code`` is the code of the largest bucket (``None`` when
    empty); ``n_codes`` is the number of distinct canonical codes present.
    """

    buckets: list[ReasonBucket]
    total: int
    dominant_code: str | None
    n_codes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "buckets": [b.as_dict() for b in self.buckets],
            "total": self.total,
            "dominant_code": self.dominant_code,
            "n_codes": self.n_codes,
        }


def canonical_reason(text: str) -> str:
    """Normalize a free-text retraction reason into a canonical code (§25.12).

    Lower-cases ``text`` and returns the first code from :data:`_REASON_KEYWORDS`
    whose any keyword is a substring; falls back to :data:`OTHER`. Codes are one of
    ``{superseded, error, duplicate, withdrawn, other}``.
    """
    low = str(text).lower()
    for code, keywords in _REASON_KEYWORDS:
        if any(kw in low for kw in keywords):
            return code
    return OTHER


def build_taxonomy(records: Iterable[dict[str, Any]], max_examples: int = 3) -> ReasonTaxonomy:
    """Aggregate ``records`` into a :class:`ReasonTaxonomy` of reason buckets (§25.12).

    Each record's ``reason`` is normalized with :func:`canonical_reason`; records
    are grouped by code into buckets carrying ``count``, ``share`` (``count/total``)
    and up to ``max_examples`` example reason strings. Buckets are sorted descending
    by count (ties broken by code for stable output); ``dominant_code`` is the top
    bucket's code, or ``None`` when there are no records.
    """
    items = list(records)
    total = len(items)

    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for rec in items:
        code = canonical_reason(rec.get("reason", ""))
        counts[code] = counts.get(code, 0) + 1
        bucket_examples = examples.setdefault(code, [])
        if len(bucket_examples) < max_examples:
            bucket_examples.append(str(rec.get("reason", "")))

    buckets = [
        ReasonBucket(
            code=code,
            count=count,
            share=(count / total if total else 0.0),
            examples=examples[code],
        )
        for code, count in counts.items()
    ]
    buckets.sort(key=lambda b: (-b.count, b.code))

    dominant_code = buckets[0].code if buckets else None
    return ReasonTaxonomy(
        buckets=buckets,
        total=total,
        dominant_code=dominant_code,
        n_codes=len(buckets),
    )
