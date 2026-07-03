"""Extraction blind-spot report — mentioned-but-not-observed (§25.14).

A *blind spot* (слепое пятно) is a ``(material, property)`` cell where the corpus
clearly *talks about* the material — it is MENTIONED (упоминается) in the prose of
one or more documents — yet carries **no** ``Measurement`` (наблюдение) of the
property. That is precisely where the extractor most plausibly missed a datum: the
material is well-discussed, so the absence of a measurement reads as an extraction
gap rather than a genuine real-world absence (cf. the §25.11 *possible_miss*).

This module is a thin *reporting* layer built entirely on top of
:mod:`kg_retrievers.mentions_lineage`. It reuses, without duplicating, the two
lineage primitives:

- :func:`~kg_retrievers.mentions_lineage.documents_mentioning` — the documents that
  name a material (its *mention count* is how many name it);
- :func:`~kg_retrievers.mentions_lineage.is_mentioned_without_observation` — the
  per-cell *mentioned-but-unmeasured* test.

:func:`build_blindspot_report` walks every ``Material`` node against every named
``Property`` node, collects the blind-spot cells, ranks them by mention count
(most-discussed-yet-unmeasured first) and rolls them up into a per-property
aggregation plus overall totals.

The ``mentions`` count is always **per material**: only materials are MENTIONS
targets, never properties, so a blind spot is a heavily-mentioned material whose
property was never measured. Aggregates (``by_property`` / ``totals``) always
summarise the *full* set of blind spots; ``top`` caps only the displayed
``blindspots`` list, never the aggregation.

Strictly read-only: it never writes to the graph. All node reads use base columns
(``id`` / ``label`` / ``property_name``) that are real queryable Kuzu columns.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.mentions_lineage import (
    documents_mentioning,
    is_mentioned_without_observation,
)

_log = get_logger("blindspot_report")

# Default number of top blind-spot cells surfaced in the ranked ``blindspots`` list.
DEFAULT_TOP = 20


@dataclass(frozen=True)
class Blindspot:
    """One mentioned-but-unmeasured ``(material, property)`` cell (§25.14).

    ``mentions`` is the number of documents that MENTION the material; ``documents``
    are their sorted, distinct ids (the provenance behind the count).
    """

    material_id: str
    property_name: str
    mentions: int
    documents: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "material_id": self.material_id,
            "property_name": self.property_name,
            "mentions": self.mentions,
            "documents": list(self.documents),
        }


@dataclass(frozen=True)
class PropertyBlindspot:
    """Per-property rollup of blind spots for one property (§25.14).

    ``n_blindspots`` counts the cells for the property; ``total_mentions`` sums their
    mention counts; ``materials`` are the sorted, distinct blind-spot materials.
    """

    property_name: str
    n_blindspots: int
    total_mentions: int
    materials: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "property_name": self.property_name,
            "n_blindspots": self.n_blindspots,
            "total_mentions": self.total_mentions,
            "materials": list(self.materials),
        }


@dataclass(frozen=True)
class BlindspotReport:
    """Ranked blind-spot cells + per-property aggregation + totals (§25.14).

    ``blindspots`` is the ``top``-capped, mention-ranked view; ``by_property`` and
    ``totals`` always summarise the *full* set of blind spots (unaffected by ``top``).
    """

    blindspots: tuple[Blindspot, ...]
    by_property: dict[str, PropertyBlindspot]
    totals: dict[str, int]

    def as_dict(self) -> dict:
        return {
            "blindspots": [b.as_dict() for b in self.blindspots],
            "by_property": {k: v.as_dict() for k, v in self.by_property.items()},
            "totals": dict(self.totals),
        }


def _materials(store: KuzuGraphStore) -> list[str]:
    """Ids of every ``Material`` node, sorted (base-column read)."""
    rows = store.rows("MATCH (n:Node) WHERE n.label='Material' RETURN n.id ORDER BY n.id")
    return [r[0] for r in rows]


def _property_names(store: KuzuGraphStore) -> list[str]:
    """Distinct property names over all ``Property`` nodes, sorted (§25.14).

    ``property_name`` is a real queryable base column; a node carrying only ``name``
    falls back to it. Duplicates (two Property nodes, one name) collapse to one cell.
    """
    rows = store.rows("MATCH (n:Node) WHERE n.label='Property' RETURN n.property_name, n.name")
    names: set[str] = set()
    for property_name, name in rows:
        resolved = property_name or name
        if resolved:
            names.add(resolved)
    return sorted(names)


def _aggregate_by_property(cells: list[Blindspot]) -> dict[str, PropertyBlindspot]:
    """Roll blind-spot cells up per property, keyed and iterated by name (§25.14)."""
    by_property: dict[str, PropertyBlindspot] = {}
    for name in sorted({c.property_name for c in cells}):
        p_cells = [c for c in cells if c.property_name == name]
        by_property[name] = PropertyBlindspot(
            property_name=name,
            n_blindspots=len(p_cells),
            total_mentions=sum(c.mentions for c in p_cells),
            materials=tuple(sorted({c.material_id for c in p_cells})),
        )
    return by_property


def _totals(cells: list[Blindspot]) -> dict[str, int]:
    """Overall counts over the full blind-spot set (all zeros when empty, §25.14)."""
    return {
        "n_blindspots": len(cells),
        "n_materials": len({c.material_id for c in cells}),
        "n_properties": len({c.property_name for c in cells}),
        "total_mentions": sum(c.mentions for c in cells),
    }


def build_blindspot_report(store: KuzuGraphStore, *, top: int = DEFAULT_TOP) -> BlindspotReport:
    """Build the extraction blind-spot report over a graph store (§25.14).

    Walks every ``Material`` node against every named ``Property`` node and keeps the
    ``(material, property)`` cells that are MENTIONED yet unmeasured — reusing
    ``documents_mentioning`` (for the mention count and the mentioned short-circuit)
    and ``is_mentioned_without_observation`` (for the per-cell test). Cells are ranked
    by mention count descending, ties broken by ``(material_id, property_name)``.

    ``top`` caps only the ranked ``blindspots`` list; ``by_property`` and ``totals``
    summarise the full set. An empty graph yields empty lists and zeroed totals.
    """
    materials = _materials(store)
    properties = _property_names(store)

    cells: list[Blindspot] = []
    for material_id in materials:
        docs = documents_mentioning(store, material_id)
        if not docs:
            continue  # never mentioned → cannot be a blind spot for any property
        mentions = len(docs)
        for property_name in properties:
            if is_mentioned_without_observation(store, material_id, property_name):
                cells.append(
                    Blindspot(
                        material_id=material_id,
                        property_name=property_name,
                        mentions=mentions,
                        documents=tuple(docs),
                    )
                )

    cells.sort(key=lambda c: (-c.mentions, c.material_id, c.property_name))

    by_property = _aggregate_by_property(cells)
    totals = _totals(cells)
    _log.info("blindspot_report.built", top=top, **totals)
    return BlindspotReport(
        blindspots=tuple(cells[: max(top, 0)]),
        by_property=by_property,
        totals=totals,
    )
