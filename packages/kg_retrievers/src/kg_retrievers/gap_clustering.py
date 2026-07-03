"""Gap clustering by shared material / property / domain (§15.12).

The gap scanner (:mod:`kg_retrievers.gap_analysis`, §15) materializes many
``Gap`` nodes; §15.9 (:mod:`kg_retrievers.gap_scoring`) scores a single gap and
§15.6 (:mod:`kg_retrievers.gap_dashboard`) rolls them into buckets. §15.12 goes
one step further and *clusters* gaps that describe the same missing corner of the
knowledge graph, so a curator can close a whole family of gaps with one campaign
instead of chasing them one by one.

Two gaps land in the same cluster when they share a **composite key**, chosen by
a fallback chain (по цепочке приоритетов):

1. **material + property** — тот же материал и то же свойство: the strongest signal
   that the gaps are the same missing measurement. Used whenever the gap carries a
   ``material_id`` and/or a ``property_id``.
2. **domain** — иначе предметная область: gaps with no material/property but a shared
   ``domain`` cluster together (§24).
3. **type** — иначе тип пробела: the last resort groups gaps only by their ``type``.

Each :class:`GapCluster` also reports its ``dominant_type`` — the modal (most
frequent) ``type`` among its members, наиболее частый тип — so the curator sees at
a glance what kind of hole the cluster represents.

Pure python — no graph or store access; the caller assembles the gap dicts
(shape ``{id, material_id?, property_id?, domain?, type}``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# Sentinel key for a gap carrying none of material/property/domain/type (§15.12).
UNCLUSTERED_KEY = "unclustered"


@dataclass(frozen=True)
class GapCluster:
    """A family of gaps sharing one composite key (§15.12).

    ``key`` is the composite grouping key (material+property, else domain, else
    type); ``gap_ids`` are the member gap ids in first-seen order; ``size`` is the
    member count; ``dominant_type`` is the modal ``type`` among members (``None``
    when no member declares a type).
    """

    key: str
    gap_ids: tuple[str, ...]
    size: int
    dominant_type: str | None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "gap_ids": list(self.gap_ids),
            "size": self.size,
            "dominant_type": self.dominant_type,
        }


def _text(value: object) -> str:
    """A trimmed non-empty string, else ``""`` for ``None`` / non-str / blank."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def cluster_key(gap: dict) -> str:
    """Composite grouping key for a single gap via the §15.12 fallback chain.

    Material + property when either is present, иначе domain, иначе type; a gap
    with none of the four falls back to :data:`UNCLUSTERED_KEY`.
    """
    material = _text(gap.get("material_id"))
    prop = _text(gap.get("property_id"))
    if material or prop:
        return f"material={material}|property={prop}"
    domain = _text(gap.get("domain"))
    if domain:
        return f"domain={domain}"
    gap_type = _text(gap.get("type"))
    if gap_type:
        return f"type={gap_type}"
    return UNCLUSTERED_KEY


def _dominant_type(gaps: list[dict]) -> str | None:
    """Modal ``type`` among ``gaps`` — most frequent, ties broken by earliest seen."""
    present = [t for t in (_text(g.get("type")) for g in gaps) if t]
    if not present:
        return None
    counts = Counter(present)
    best = max(counts.values())
    # Walk in insertion order so a tie resolves to the first-appearing modal type.
    return next(t for t in present if counts[t] == best)


def cluster_gaps(gaps: list[dict]) -> list[GapCluster]:
    """Group ``gaps`` into :class:`GapCluster` families by composite key (§15.12).

    Gaps are bucketed by :func:`cluster_key`; clusters come out in first-seen key
    order (deterministic). Each cluster keeps its members' ids in encounter order
    and reports the modal member ``type`` as ``dominant_type``. ``[]`` → ``[]``.
    """
    buckets: dict[str, list[dict]] = {}
    for gap in gaps:
        buckets.setdefault(cluster_key(gap), []).append(gap)
    clusters: list[GapCluster] = []
    for key, members in buckets.items():
        gap_ids = tuple(str(g.get("id")) for g in members)
        clusters.append(
            GapCluster(
                key=key,
                gap_ids=gap_ids,
                size=len(members),
                dominant_type=_dominant_type(members),
            )
        )
    return clusters


def rank_clusters(clusters: list[GapCluster]) -> list[GapCluster]:
    """Return ``clusters`` ranked by ``size`` descending (§15.12).

    Stable sort — equal-size clusters keep their input (first-seen) order, so the
    ranking is deterministic.
    """
    return sorted(clusters, key=lambda c: c.size, reverse=True)
