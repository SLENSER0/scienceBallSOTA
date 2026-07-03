"""§15.3 ``missing_regime`` gap subtype over the graph store.

Подтип пробела «отсутствует технологический режим». This is the *inverse* of the
``missing_property_value`` subtype: there the property value is absent; here the
property **value is present** on a Measurement, but the measurement (or its owning
``Sample`` / ``Experiment``) is **not** linked to any ``ProcessingRegime``. Without a
regime the number is un-contextualised — it cannot be compared, contradicted or
placed on the coverage cube (materials × regimes × property), so it is a real gap.

A Measurement is considered *regime-covered* when it has an
``ABOUT_REGIME`` / ``PROCESSED_BY`` path to a ``ProcessingRegime`` node — either

- directly (``Measurement -[ABOUT_REGIME|PROCESSED_BY]-> ProcessingRegime``), or
- through its owner (``Measurement - Sample|Experiment -[PROCESSED_BY]-> ProcessingRegime``).

Every Measurement that is **not** regime-covered yields one
:class:`MissingRegimeGap` tagged ``subtype='missing_regime'``.

Kuzu note: custom node props are **not** queryable columns, so the store is queried
for base columns / ids only (``n.id`` / ``n.label`` / ``e.type``) and never for
ad-hoc property keys. The ``subject`` / ``property`` are read from the Measurement's
``ABOUT_MATERIAL`` / ``OF_PROPERTY`` edges, both optional.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

__all__ = ["MissingRegimeGap", "find_missing_regime_gaps"]

# Edge types that attach a Measurement (or its owner) to a ProcessingRegime.
_REGIME_EDGES = ("ABOUT_REGIME", "PROCESSED_BY")
# Owner labels whose PROCESSED_BY regime also covers the measurement.
_OWNER_LABELS = ("Sample", "Experiment")


@dataclass(frozen=True)
class MissingRegimeGap:
    """One §15.3 ``missing_regime`` gap for a regime-less Measurement.

    ``measurement_id`` is the Measurement whose value lacks a processing context.
    ``subject_id`` is the material/solution it is ``ABOUT_MATERIAL`` (empty string
    when no such edge exists). ``property_id`` is the ``Property`` it is
    ``OF_PROPERTY`` (``None`` when absent). ``subtype`` is fixed to
    ``'missing_regime'`` so callers can bucket it alongside the other §15.3 subtypes.
    """

    measurement_id: str
    subject_id: str
    property_id: str | None
    subtype: str = "missing_regime"

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-ready) — сериализация в словарь."""
        return asdict(self)


def _measurements_with_regime(store: KuzuGraphStore) -> set[str]:
    """Measurement ids that have an ``ABOUT_REGIME`` / ``PROCESSED_BY`` regime path.

    Covers both the direct edge and the owner (``Sample`` / ``Experiment``) hop.
    Множество измерений, покрытых технологическим режимом.
    """
    covered: set[str] = set()
    types = list(_REGIME_EDGES)
    # Direct: Measurement -[ABOUT_REGIME|PROCESSED_BY]-> ProcessingRegime.
    for (mid,) in store.rows(
        "MATCH (m:Node)-[e:Rel]->(g:Node) "
        "WHERE m.label='Measurement' AND e.type IN $types AND g.label='ProcessingRegime' "
        "RETURN DISTINCT m.id",
        {"types": types},
    ):
        covered.add(mid)
    # Owner hop: Measurement - Sample|Experiment -[PROCESSED_BY]-> ProcessingRegime.
    for (mid,) in store.rows(
        "MATCH (m:Node)-[:Rel]-(o:Node)-[e:Rel]->(g:Node) "
        "WHERE m.label='Measurement' AND o.label IN $owners "
        "AND e.type='PROCESSED_BY' AND g.label='ProcessingRegime' "
        "RETURN DISTINCT m.id",
        {"owners": list(_OWNER_LABELS)},
    ):
        covered.add(mid)
    return covered


def _measurement_ids(store: KuzuGraphStore, *, limit: int) -> list[str]:
    """All Measurement ids, sorted for determinism (детерминированный порядок)."""
    return [
        mid
        for (mid,) in store.rows(
            "MATCH (m:Node) WHERE m.label='Measurement' RETURN m.id ORDER BY m.id LIMIT $lim",
            {"lim": limit},
        )
    ]


def _subject_of(store: KuzuGraphStore) -> dict[str, str]:
    """Map each Measurement to the material/solution it is ``ABOUT_MATERIAL``."""
    return dict(
        store.rows(
            "MATCH (m:Node)-[e:Rel]->(s:Node) "
            "WHERE m.label='Measurement' AND e.type='ABOUT_MATERIAL' "
            "RETURN m.id, s.id"
        )
    )


def _property_of(store: KuzuGraphStore) -> dict[str, str]:
    """Map each Measurement to the ``Property`` it is ``OF_PROPERTY``."""
    return dict(
        store.rows(
            "MATCH (m:Node)-[e:Rel]->(p:Node) "
            "WHERE m.label='Measurement' AND e.type='OF_PROPERTY' AND p.label='Property' "
            "RETURN m.id, p.id"
        )
    )


def find_missing_regime_gaps(store: KuzuGraphStore, *, limit: int = 5000) -> list[MissingRegimeGap]:
    """Find §15.3 ``missing_regime`` gaps: Measurements with no ProcessingRegime.

    Enumerates every ``Measurement`` node, subtracts those with an
    ``ABOUT_REGIME`` / ``PROCESSED_BY`` regime path, and emits one
    :class:`MissingRegimeGap` per regime-less measurement. ``subject_id`` /
    ``property_id`` are read from the ``ABOUT_MATERIAL`` / ``OF_PROPERTY`` edges when
    present. Results are sorted by ``measurement_id`` for determinism.
    """
    covered = _measurements_with_regime(store)
    subjects = _subject_of(store)
    properties = _property_of(store)
    gaps: list[MissingRegimeGap] = []
    for mid in _measurement_ids(store, limit=limit):
        if mid in covered:
            continue
        gaps.append(
            MissingRegimeGap(
                measurement_id=mid,
                subject_id=subjects.get(mid, ""),
                property_id=properties.get(mid),
            )
        )
    gaps.sort(key=lambda g: g.measurement_id)
    return gaps
