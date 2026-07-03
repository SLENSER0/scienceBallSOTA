"""Source grouping for the 'литературный обзор' answer format (§24.11).

Аналитика/синтез — группировка источников. Для формата ответа «литературный
обзор» источники нужно разложить по четырём осям: по методу (``method``), по году
(``year``), по географии (``geography``) и по силе доказательности
(``evidence_strength``). Каждый источник — это запись с обязательным ``source_id`` и
необязательными полями оси; отсутствующее или пустое значение поля отправляет
источник в корзину ``'unknown'``. Внутри корзины ``source_id`` уникальны и
отсортированы, год приводится к строке.

English: :func:`group_sources` buckets literature-review sources along four axes —
method, year, geography and evidence strength. A record is a ``dict`` with a
required ``source_id`` and optional axis fields; a missing or blank axis value
routes the source into the ``'unknown'`` bucket. Within a bucket the ``source_id``
values are de-duplicated and sorted, and ``year`` is coerced to ``str`` so ``2021``
and ``'2021'`` share the ``'2021'`` key. :func:`bucket_counts` reduces the buckets to
per-key source counts. The module is pure: it reads only the given records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Bucket key used when an axis value is missing or blank (корзина «неизвестно»).
UNKNOWN_BUCKET = "unknown"

# The four grouping axes, in canonical order (§24.11 «группировка источников»).
AXES: tuple[str, ...] = ("method", "year", "geography", "evidence_strength")


@dataclass(frozen=True)
class ReviewBuckets:
    """Literature-review sources grouped along four axes (§24.11).

    Each ``by_*`` maps a bucket key to a sorted tuple of distinct ``source_id`` values:
    ``by_method`` (по методу), ``by_year`` (по году, ключ — строка), ``by_geography``
    (по географии) and ``by_evidence_strength`` (по силе доказательности). ``total`` is
    the count of distinct ``source_id`` across all input records.
    """

    by_method: dict[str, tuple[str, ...]]
    by_year: dict[str, tuple[str, ...]]
    by_geography: dict[str, tuple[str, ...]]
    by_evidence_strength: dict[str, tuple[str, ...]]
    total: int

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{by_method, by_year, by_geography, by_evidence_strength, total}``.

        The four bucket dicts round-trip losslessly: keys preserved, ``source_id`` tuples
        materialised as lists so the result is plain JSON.
        """
        return {
            "by_method": {k: list(v) for k, v in self.by_method.items()},
            "by_year": {k: list(v) for k, v in self.by_year.items()},
            "by_geography": {k: list(v) for k, v in self.by_geography.items()},
            "by_evidence_strength": {k: list(v) for k, v in self.by_evidence_strength.items()},
            "total": self.total,
        }


def _bucket_key(value: object) -> str:
    """Coerce an axis value to a bucket key; blank / missing -> :data:`UNKNOWN_BUCKET`.

    Non-string values (e.g. an ``int`` year ``2021``) are stringified, then stripped;
    an empty result routes into the ``'unknown'`` bucket.
    """
    if value is None:
        return UNKNOWN_BUCKET
    key = str(value).strip()
    return key or UNKNOWN_BUCKET


def _source_id(record: dict[str, Any]) -> str | None:
    """A record's ``source_id`` as a non-empty, stripped ``str`` (else ``None``)."""
    raw = record.get("source_id")
    if raw is None:
        return None
    sid = str(raw).strip()
    return sid or None


def _finalise(buckets: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    """Freeze ``key -> set`` into ``key -> sorted tuple`` for a deterministic result."""
    return {key: tuple(sorted(ids)) for key, ids in buckets.items()}


def group_sources(records: list[dict[str, Any]]) -> ReviewBuckets:
    """Group review sources by method, year, geography and evidence strength (§24.11).

    Each record contributes its ``source_id`` to one key per axis: the axis field value
    (missing / blank -> ``'unknown'``, ``year`` coerced to ``str``). ``source_id`` values
    are de-duplicated within every bucket and the buckets are sorted. ``total`` counts the
    distinct ``source_id`` seen. Records without a usable ``source_id`` are skipped.
    """
    axis_buckets: dict[str, dict[str, set[str]]] = {axis: {} for axis in AXES}
    seen_ids: set[str] = set()

    for record in records:
        sid = _source_id(record)
        if sid is None:
            continue
        seen_ids.add(sid)
        for axis in AXES:
            key = _bucket_key(record.get(axis))
            axis_buckets[axis].setdefault(key, set()).add(sid)

    return ReviewBuckets(
        by_method=_finalise(axis_buckets["method"]),
        by_year=_finalise(axis_buckets["year"]),
        by_geography=_finalise(axis_buckets["geography"]),
        by_evidence_strength=_finalise(axis_buckets["evidence_strength"]),
        total=len(seen_ids),
    )


def bucket_counts(buckets: ReviewBuckets) -> dict[str, dict[str, int]]:
    """Per-axis ``key -> number of distinct source_id`` view of ``buckets`` (§24.11).

    Returns ``{'by_method': {key: len, ...}, 'by_year': {...}, 'by_geography': {...},
    'by_evidence_strength': {...}}`` — the same keys as the buckets, each mapped to its
    source count for a quick hand-checkable summary.
    """
    return {
        "by_method": {k: len(v) for k, v in buckets.by_method.items()},
        "by_year": {k: len(v) for k, v in buckets.by_year.items()},
        "by_geography": {k: len(v) for k, v in buckets.by_geography.items()},
        "by_evidence_strength": {k: len(v) for k, v in buckets.by_evidence_strength.items()},
    }
