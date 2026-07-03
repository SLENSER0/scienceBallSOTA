"""Literature-review facet grouping for answer synthesis (§24.11).

Groups source records by one of the four §24.11 «literature-review» facets —
*method* / *year* / *geography* / *evidence_strength* — which the existing
``synthesis_consensus`` does not do. Each facet bucket collects the deduplicated
source ids and an evidence-strength histogram so the analytics layer can render
«сколько источников по методу / году / географии / силе доказательств».

Группирует записи источников по одному из четырёх фасетов §24.11
(метод / год / география / сила доказательств). Существующий
``synthesis_consensus`` этого не делает.

Bucketing rules:
- a source missing the facet key is bucketed under key ``'unknown'``;
- ``source_ids`` are deduplicated within a bucket (a repeated id counts once);
- ``n_sources`` is the number of distinct source ids in the bucket;
- ``evidence_strength_hist`` counts distinct sources per evidence-strength value;
- buckets are sorted by ``n_sources`` descending, then by ``key`` ascending.

Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Facets permitted by §24.11 for literature-review grouping.
VALID_FACETS: tuple[str, ...] = ("method", "year", "geography", "evidence_strength")

#: Key used when a source record is missing the requested facet.
UNKNOWN_KEY: str = "unknown"


@dataclass(frozen=True)
class FacetBucket:
    """One §24.11 facet bucket over grouped source records.

    - ``facet`` — the facet grouped on (one of :data:`VALID_FACETS`);
    - ``key`` — the facet value for this bucket (``'unknown'`` if missing);
    - ``source_ids`` — deduplicated source ids in stable first-seen order;
    - ``n_sources`` — number of distinct source ids in the bucket;
    - ``evidence_strength_hist`` — distinct-source counts per evidence strength.
    """

    facet: str
    key: str
    source_ids: tuple[str, ...]
    n_sources: int
    evidence_strength_hist: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping of this bucket."""
        return {
            "facet": self.facet,
            "key": self.key,
            "source_ids": list(self.source_ids),
            "n_sources": self.n_sources,
            "evidence_strength_hist": dict(self.evidence_strength_hist),
        }


def group_by_facet(sources: list[dict], facet: str) -> tuple[FacetBucket, ...]:
    """Group ``sources`` into §24.11 :class:`FacetBucket` tuples by ``facet``.

    Each source dict is ``{source_id, method, year, geography,
    evidence_strength}``. Records missing the facet key land in the
    ``'unknown'`` bucket. Source ids are deduplicated within a bucket (a
    repeated id counts once). Buckets are sorted by ``n_sources`` descending,
    then by ``key`` ascending.

    Каждая запись источника группируется по указанному фасету; отсутствующий
    ключ фасета попадает в ведро ``'unknown'``.

    :raises ValueError: if ``facet`` is not one of :data:`VALID_FACETS`.
    """
    if facet not in VALID_FACETS:
        raise ValueError(f"unknown facet {facet!r}; expected one of {VALID_FACETS}")

    # Preserve first-seen key order for deterministic pre-sort grouping.
    ids_by_key: dict[str, list[str]] = {}
    seen_by_key: dict[str, set[str]] = {}
    hist_by_key: dict[str, dict[str, int]] = {}

    for source in sources:
        raw_key = source.get(facet)
        key = UNKNOWN_KEY if raw_key is None else str(raw_key)
        source_id = str(source.get("source_id"))

        seen = seen_by_key.setdefault(key, set())
        if source_id in seen:
            continue
        seen.add(source_id)
        ids_by_key.setdefault(key, []).append(source_id)

        strength = source.get("evidence_strength")
        if strength is not None:
            hist = hist_by_key.setdefault(key, {})
            strength_key = str(strength)
            hist[strength_key] = hist.get(strength_key, 0) + 1

    buckets = [
        FacetBucket(
            facet=facet,
            key=key,
            source_ids=tuple(ids),
            n_sources=len(ids),
            evidence_strength_hist=dict(hist_by_key.get(key, {})),
        )
        for key, ids in ids_by_key.items()
    ]
    buckets.sort(key=lambda b: (-b.n_sources, b.key))
    return tuple(buckets)
