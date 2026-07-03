"""Near-miss gap enumeration over a MENTIONS graph (§25.8).

A *near-miss* (почти-промах) is a ``(material, property)`` pair that the corpus
*mentions* — the material is named in at least one ``Document`` — yet for which
no ``Observation`` (a ``Measurement`` of that property) exists. These are the
highest-yield extraction gaps: the material is demonstrably in scope of the
literature, so a missing datum (наблюдение) more plausibly reflects an extractor
miss than a genuine, real absence.

This module builds on the §25.7 MENTIONS-lineage helpers
(:func:`~kg_retrievers.mentions_lineage.documents_mentioning` and
``_has_observation``) and enumerates candidates over a candidate grid of
materials × properties. It is strictly read-only over a :class:`KuzuGraphStore`.

    :func:`find_near_miss_gaps` — emit a :class:`NearMissCandidate` for every
    ``(material, property)`` that is mentioned but unobserved, rolled up into a
    sorted :class:`NearMissReport`.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.mentions_lineage import _has_observation, documents_mentioning

_log = get_logger("near_miss_gaps")


@dataclass(frozen=True)
class NearMissCandidate:
    """A single near-miss ``(material, property)`` gap candidate (§25.8).

    ``material_id`` is mentioned in ``doc_ids`` (>=1 document) yet has no
    ``Observation`` of ``property_name`` — ``has_observation`` is therefore
    always ``False`` for an emitted candidate (kept explicit for serialisation).
    """

    material_id: str
    property_name: str
    doc_ids: list[str]
    has_observation: bool = False

    def as_dict(self) -> dict:
        return {
            "material_id": self.material_id,
            "property_name": self.property_name,
            "doc_ids": list(self.doc_ids),
            "has_observation": self.has_observation,
        }


@dataclass(frozen=True)
class NearMissReport:
    """Aggregate near-miss report over a materials × properties grid (§25.8).

    ``candidates`` is sorted by ``(material_id, property_name)``; ``n_candidates``
    equals ``len(candidates)``.
    """

    candidates: list[NearMissCandidate]
    n_candidates: int

    def as_dict(self) -> dict:
        return {
            "candidates": [c.as_dict() for c in self.candidates],
            "n_candidates": self.n_candidates,
        }


def find_near_miss_gaps(
    store: KuzuGraphStore, materials: list[str], properties: list[str]
) -> NearMissReport:
    """Enumerate near-miss ``(material, property)`` gaps over a grid (§25.8).

    For each ``material_id`` in ``materials`` (duplicates collapsed, order kept)
    a candidate is emitted for each ``property_name`` in ``properties`` **only**
    when the material is mentioned in at least one document AND has no
    ``Observation`` (Measurement) of that property. Materials mentioned by no
    document contribute nothing. The result is sorted by
    ``(material_id, property_name)`` with ``n_candidates == len(candidates)``.
    """
    candidates: list[NearMissCandidate] = []
    for material_id in dict.fromkeys(materials):
        doc_ids = documents_mentioning(store, material_id)
        if not doc_ids:
            continue  # not mentioned anywhere → not in scope, no near-miss
        for property_name in dict.fromkeys(properties):
            if _has_observation(store, material_id, property_name):
                continue  # already observed → not a gap
            candidates.append(
                NearMissCandidate(
                    material_id=material_id,
                    property_name=property_name,
                    doc_ids=doc_ids,
                    has_observation=False,
                )
            )
    candidates.sort(key=lambda c: (c.material_id, c.property_name))
    _log.info("near_miss_gaps.built", n_candidates=len(candidates))
    return NearMissReport(candidates=candidates, n_candidates=len(candidates))
