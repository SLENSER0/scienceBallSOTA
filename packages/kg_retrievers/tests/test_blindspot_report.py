"""Extraction blind-spot report over a hand-built graph (§25.14).

Corpus (no seed dependency — the seed carries no MENTIONS edges):

    Document(doc1)-HAS_CHUNK->Chunk(c1)-MENTIONS->{nickel, copper}
    Document(doc2)-HAS_CHUNK->Chunk(c2)-MENTIONS->{nickel}
    Document(doc3)-HAS_CHUNK->Chunk(c3)-MENTIONS->{nickel}
    Measurement(recovery) -ABOUT_MATERIAL-> nickel   (an observation of 'recovery')
    Property nodes: recovery, conductivity ; Material cobalt exists but is unmentioned

Hand-checked mention counts: nickel = 3 docs, copper = 1 doc, cobalt = 0.

Grid materials × {conductivity, recovery} → blind spots (mentioned & unmeasured):
    (nickel, conductivity)  mentions=3    (nickel has NO conductivity Measurement)
    (copper, conductivity)  mentions=1
    (copper, recovery)      mentions=1
NOT a blind spot: (nickel, recovery) — nickel has a 'recovery' Measurement;
                  any cobalt cell — cobalt is never mentioned.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.blindspot_report import (
    DEFAULT_TOP,
    Blindspot,
    BlindspotReport,
    PropertyBlindspot,
    build_blindspot_report,
)
from kg_retrievers.graph_store import KuzuGraphStore

DOC1 = make_id("Document", "doc one")
DOC2 = make_id("Document", "doc two")
DOC3 = make_id("Document", "doc three")
C1 = make_id("Chunk", "chunk one")
C2 = make_id("Chunk", "chunk two")
C3 = make_id("Chunk", "chunk three")
NICKEL = make_id("Material", "nickel")
COPPER = make_id("Material", "copper")
COBALT = make_id("Material", "cobalt")
PROP_RECOVERY = make_id("Property", "recovery")
PROP_CONDUCTIVITY = make_id("Property", "conductivity")


def _build_corpus(s: KuzuGraphStore) -> None:
    """Three docs mentioning materials + one 'recovery' measurement on nickel."""
    s.upsert_node(DOC1, "Document", name="Doc One")
    s.upsert_node(DOC2, "Document", name="Doc Two")
    s.upsert_node(DOC3, "Document", name="Doc Three")
    s.upsert_node(C1, "Chunk", text="nickel and copper leaching")
    s.upsert_node(C2, "Chunk", text="nickel electrowinning")
    s.upsert_node(C3, "Chunk", text="nickel roasting")
    s.upsert_node(NICKEL, "Material", name="nickel", domain="hydrometallurgy")
    s.upsert_node(COPPER, "Material", name="copper", domain="hydrometallurgy")
    s.upsert_node(COBALT, "Material", name="cobalt", domain="hydrometallurgy")
    s.upsert_node(PROP_RECOVERY, "Property", property_name="recovery", name="Recovery")
    s.upsert_node(PROP_CONDUCTIVITY, "Property", property_name="conductivity", name="Conductivity")

    meas = make_id("Measurement", "nickel recovery")
    s.upsert_node(meas, "Measurement", property_name="recovery", value_normalized=92.0)

    s.upsert_edge(DOC1, C1, "HAS_CHUNK")
    s.upsert_edge(DOC2, C2, "HAS_CHUNK")
    s.upsert_edge(DOC3, C3, "HAS_CHUNK")
    s.upsert_edge(C1, NICKEL, "MENTIONS")
    s.upsert_edge(C1, COPPER, "MENTIONS")
    s.upsert_edge(C2, NICKEL, "MENTIONS")
    s.upsert_edge(C3, NICKEL, "MENTIONS")
    s.upsert_edge(meas, NICKEL, "ABOUT_MATERIAL", confidence=0.9)


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build_corpus(s)
    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "empty"))
    yield s
    s.close()


def _cell(report: BlindspotReport, material_id: str, property_name: str) -> Blindspot | None:
    for b in report.blindspots:
        if b.material_id == material_id and b.property_name == property_name:
            return b
    return None


# -- a mentioned-but-unmeasured cell IS a blind spot -----------------------
def test_mentioned_unmeasured_cell_is_a_blindspot(store: KuzuGraphStore) -> None:
    report = build_blindspot_report(store)
    cell = _cell(report, NICKEL, "conductivity")
    assert cell is not None  # nickel is mentioned but has no conductivity Measurement
    assert cell.mentions == 3  # doc1 + doc2 + doc3
    assert cell.documents == (DOC1, DOC3, DOC2)  # sorted by id: one < three < two


# -- a measured cell is NOT a blind spot -----------------------------------
def test_measured_cell_is_not_a_blindspot(store: KuzuGraphStore) -> None:
    report = build_blindspot_report(store)
    # nickel HAS a 'recovery' Measurement → (nickel, recovery) must be absent.
    assert _cell(report, NICKEL, "recovery") is None
    # cobalt is never mentioned → no cobalt cell for any property.
    assert not any(b.material_id == COBALT for b in report.blindspots)


# -- exactly the three expected blind spots --------------------------------
def test_blindspot_set_is_exact(store: KuzuGraphStore) -> None:
    report = build_blindspot_report(store)
    got = {(b.material_id, b.property_name) for b in report.blindspots}
    assert got == {
        (NICKEL, "conductivity"),
        (COPPER, "conductivity"),
        (COPPER, "recovery"),
    }


# -- ranked by mention count (desc), ties by (material, property) ----------
def test_ranked_by_mention_count(store: KuzuGraphStore) -> None:
    report = build_blindspot_report(store)
    ranked = [(b.material_id, b.property_name, b.mentions) for b in report.blindspots]
    assert ranked == [
        (NICKEL, "conductivity", 3),  # highest mention count first
        (COPPER, "conductivity", 1),  # tie at 1 → material copper, prop conductivity
        (COPPER, "recovery", 1),  # tie at 1 → then recovery
    ]


# -- per-property aggregation ----------------------------------------------
def test_by_property_aggregates(store: KuzuGraphStore) -> None:
    report = build_blindspot_report(store)
    assert set(report.by_property) == {"conductivity", "recovery"}

    conductivity = report.by_property["conductivity"]
    assert isinstance(conductivity, PropertyBlindspot)
    assert conductivity.n_blindspots == 2  # nickel + copper
    assert conductivity.total_mentions == 4  # 3 (nickel) + 1 (copper)
    assert conductivity.materials == tuple(sorted((NICKEL, COPPER)))

    recovery = report.by_property["recovery"]
    assert recovery.n_blindspots == 1  # copper only (nickel is measured)
    assert recovery.total_mentions == 1
    assert recovery.materials == (COPPER,)


# -- totals over the full set ----------------------------------------------
def test_totals(store: KuzuGraphStore) -> None:
    report = build_blindspot_report(store)
    assert report.totals == {
        "n_blindspots": 3,
        "n_materials": 2,  # nickel + copper
        "n_properties": 2,  # conductivity + recovery
        "total_mentions": 5,  # 3 + 1 + 1
    }


# -- top cap trims the list but not the aggregates -------------------------
def test_top_cap(store: KuzuGraphStore) -> None:
    report = build_blindspot_report(store, top=1)
    assert len(report.blindspots) == 1  # only the single highest-ranked cell
    assert (report.blindspots[0].material_id, report.blindspots[0].property_name) == (
        NICKEL,
        "conductivity",
    )
    # aggregates still describe all three blind spots (unaffected by top).
    assert report.totals["n_blindspots"] == 3
    assert report.by_property["conductivity"].n_blindspots == 2


def test_default_top_is_20() -> None:
    assert DEFAULT_TOP == 20


# -- empty graph → zeros ---------------------------------------------------
def test_empty_store_yields_zeros(empty_store: KuzuGraphStore) -> None:
    report = build_blindspot_report(empty_store)
    assert isinstance(report, BlindspotReport)
    assert report.blindspots == ()
    assert report.by_property == {}
    assert report.totals == {
        "n_blindspots": 0,
        "n_materials": 0,
        "n_properties": 0,
        "total_mentions": 0,
    }


# -- as_dict shape and values ----------------------------------------------
def test_as_dict_shape_and_values(store: KuzuGraphStore) -> None:
    dumped = build_blindspot_report(store).as_dict()

    assert set(dumped) == {"blindspots", "by_property", "totals"}
    assert isinstance(dumped["blindspots"], list)
    assert dumped["blindspots"][0] == {
        "material_id": NICKEL,
        "property_name": "conductivity",
        "mentions": 3,
        "documents": [DOC1, DOC3, DOC2],
    }
    assert dumped["by_property"]["recovery"] == {
        "property_name": "recovery",
        "n_blindspots": 1,
        "total_mentions": 1,
        "materials": [COPPER],
    }
    assert dumped["totals"]["total_mentions"] == 5
