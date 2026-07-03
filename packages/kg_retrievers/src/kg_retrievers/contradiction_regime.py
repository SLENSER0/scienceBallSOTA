"""Regime-aware contradiction detection over the graph store (§15.4).

Расширенное выявление противоречий с учётом технологического режима. The plain
gap scan (``gap_analysis._scan_contradictions``) keys a contradiction on *any*
shared subject and ignores confidence-interval overlap — so it wrongly flags two
measurements taken under **different processing regimes** (different ``T`` / time /
atmosphere) as contradictory, and it flags divergent point values even when their
uncertainty bands overlap.

This module fixes both. It groups Measurement nodes by
``(subject, property, ProcessingRegime)`` and flags a pair **only** when

- the two measurements share the *same* regime (разные режимы → НЕ противоречие);
- their numeric divergence ``|a-b| / max(|a|,|b|) >= min_divergence``; and
- their confidence intervals do **not** overlap (перекрывающиеся ДИ → НЕ
  противоречие).

The CI / divergence heuristics are reused verbatim from
:mod:`kg_retrievers.contradiction_detector` — this module only adds the
regime-aware grouping over :class:`~kg_retrievers.graph_store.KuzuGraphStore`.

Kuzu note: custom Measurement props (``ci_low`` / ``ci_high`` / ``evidence_ids``)
are **not** queryable columns, so the store is queried for base columns / ids only
and the full measurement dict is read back via ``store.get_node()``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from kg_retrievers.contradiction_detector import (
    DIVERGENCE_THRESHOLD,
    _as_float,
    _ci_finding,
    _same_unit,
)
from kg_retrievers.graph_store import KuzuGraphStore

__all__ = ["ContradictionPair", "find_contradictions"]

# A measurement dict as returned by ``KuzuGraphStore.get_node`` (columns + props).
Measurement = dict[str, Any]

# Group key: (subject id, property name, ProcessingRegime id).
_GroupKey = tuple[str, str, str]


@dataclass(frozen=True)
class ContradictionPair:
    """One regime-scoped contradiction between two measurements (§15.4).

    ``subject`` / ``regime`` are node ids (the material/solution the property is
    measured on, and the ``ProcessingRegime`` it was measured under). ``divergence``
    is the relative point-value gap ``|a-b| / max(|a|,|b|)``. ``ci_overlap`` records
    the confidence-interval decision — always ``False`` for a flagged pair, since an
    overlapping interval suppresses the contradiction. ``evidence_ids`` gathers the
    supporting evidence of both sides (свидетельства).
    """

    measurement_a: str
    measurement_b: str
    subject: str
    property: str
    regime: str
    divergence: float
    ci_overlap: bool
    evidence_ids: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "measurement_a": self.measurement_a,
            "measurement_b": self.measurement_b,
            "subject": self.subject,
            "property": self.property,
            "regime": self.regime,
            "divergence": self.divergence,
            "ci_overlap": self.ci_overlap,
            "evidence_ids": list(self.evidence_ids),
        }


def _relative_divergence(a: Measurement, b: Measurement) -> float | None:
    """Relative point-value gap, or ``None`` when incomparable (§15.4).

    Reuses ``contradiction_detector._same_unit`` / ``_as_float`` so the metric
    matches the plain detector exactly, but returns the raw ratio so the caller
    can compare it against a configurable ``min_divergence``.
    """
    if not _same_unit(a, b):
        return None
    va, vb = _as_float(a.get("value_normalized")), _as_float(b.get("value_normalized"))
    if va is None or vb is None:
        return None
    scale = max(abs(va), abs(vb))
    if scale == 0.0:
        return None
    return abs(va - vb) / scale


def _has_ci(m: Measurement) -> bool:
    """True when a measurement carries a fully-parsed confidence interval."""
    return _as_float(m.get("ci_low")) is not None and _as_float(m.get("ci_high")) is not None


def _ci_overlaps(a: Measurement, b: Measurement) -> bool:
    """True only when both sides have CIs that overlap (перекрытие ДИ).

    Delegates the disjoint test to ``contradiction_detector._ci_finding`` (a
    non-``None`` finding means the intervals are disjoint). When either side lacks
    a CI there is nothing to overlap, so the answer is ``False``.
    """
    if not (_has_ci(a) and _has_ci(b)):
        return False
    return _ci_finding(a, b) is None


def _regime_rows(store: KuzuGraphStore) -> list[tuple[str, str]]:
    """(measurement id, ProcessingRegime id) for every ABOUT_REGIME edge."""
    return [
        (mid, rid)
        for mid, rid in store.rows(
            "MATCH (m:Node)-[e:Rel]->(g:Node) "
            "WHERE m.label='Measurement' AND e.type='ABOUT_REGIME' "
            "AND g.label='ProcessingRegime' "
            "RETURN m.id, g.id LIMIT 5000"
        )
    ]


def _subject_of(store: KuzuGraphStore) -> dict[str, str]:
    """Map each measurement to the material/solution it is ABOUT_MATERIAL."""
    return dict(
        store.rows(
            "MATCH (m:Node)-[e:Rel]->(s:Node) "
            "WHERE m.label='Measurement' AND e.type='ABOUT_MATERIAL' "
            "RETURN m.id, s.id LIMIT 5000"
        )
    )


def _evidence_ids(store: KuzuGraphStore, mid: str, m: Measurement) -> set[str]:
    """Gather a measurement's evidence: its ``evidence_ids`` prop + Evidence nodes."""
    ids: set[str] = set()
    raw = m.get("evidence_ids")
    if isinstance(raw, list):
        ids.update(str(x) for x in raw)
    elif isinstance(raw, str) and raw:
        ids.add(raw)
    for (eid,) in store.rows(
        "MATCH (m:Node {id:$id})-[:Rel]-(e:Node) WHERE e.label='Evidence' RETURN e.id LIMIT 200",
        {"id": mid},
    ):
        ids.add(eid)
    return ids


def find_contradictions(
    store: KuzuGraphStore, *, min_divergence: float = DIVERGENCE_THRESHOLD
) -> list[ContradictionPair]:
    """Find regime-aware measurement contradictions in the store (§15.4).

    Measurements are grouped by ``(subject, property, ProcessingRegime)``; within a
    group every pair is flagged **only** when its numeric divergence is at least
    ``min_divergence`` *and* its confidence intervals do not overlap. Measurements in
    different regimes never form a pair. The result is sorted for determinism.
    """
    subjects = _subject_of(store)
    groups: dict[_GroupKey, list[str]] = defaultdict(list)
    cache: dict[str, Measurement] = {}
    for mid, rid in _regime_rows(store):
        md = cache.get(mid)
        if md is None:
            md = store.get_node(mid) or {}
            cache[mid] = md
        prop = md.get("property_name")
        if not prop or md.get("value_normalized") is None:
            continue
        subject = subjects.get(mid, rid)  # fall back to the regime when no material
        groups[(subject, str(prop), rid)].append(mid)

    pairs: list[ContradictionPair] = []
    for (subject, prop, rid), members in groups.items():
        members = sorted(set(members))
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                mid_a, mid_b = members[i], members[j]
                a, b = cache[mid_a], cache[mid_b]
                div = _relative_divergence(a, b)
                if div is None or div < min_divergence:
                    continue
                if _ci_overlaps(a, b):
                    continue
                evidence = _evidence_ids(store, mid_a, a) | _evidence_ids(store, mid_b, b)
                pairs.append(
                    ContradictionPair(
                        measurement_a=mid_a,
                        measurement_b=mid_b,
                        subject=subject,
                        property=prop,
                        regime=rid,
                        divergence=round(div, 4),
                        ci_overlap=False,
                        evidence_ids=tuple(sorted(evidence)),
                    )
                )
    pairs.sort(key=lambda p: (p.subject, p.property, p.regime, p.measurement_a, p.measurement_b))
    return pairs
