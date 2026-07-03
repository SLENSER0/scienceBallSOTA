"""[DE] value_present on prose Property MENTIONS edges (§33/N2, D2).

At ingest the pipeline stamps the measurable-value-in-mention signal (D1) on the
``Chunk-[:MENTIONS]->Property`` edge: True when the prose states a value for the
property, False when it merely names it. Material / structural edges carry no
flag. The absence value gate (D3) reads this flag; it is written for every ingest
regardless of the gate, and updates idempotently on the MERGE edge upsert.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ingestion_service.parsers import ParsedDoc
from ingestion_service.pipeline import IngestionPipeline

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore

# flow_velocity is a Property in the taxonomy whose alias "скорость циркуляции"
# appears verbatim in the prose below, so the offline detector can locate it.
FLOW_VELOCITY = make_id("Property", "flow_velocity")
NICKEL = make_id("Material", "nickel")


def _ingest(text: str, file_hash: str) -> KuzuGraphStore:
    store = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    doc = ParsedDoc(
        path="x.txt",
        title="N2",
        doc_type="article",
        file_hash=file_hash,
        lang="ru",
        pages=[(1, text)],
        country="russia",
        year=2023,
    )
    IngestionPipeline(store).ingest(doc)
    return store


def _mention_value_present(store: KuzuGraphStore, property_id: str) -> list:
    """value_present of every Chunk-[:MENTIONS]->property edge (may be [] / [None])."""
    return [
        r[0]
        for r in store.rows(
            "MATCH (c:Node)-[r:Rel]->(p:Node {id:$pid}) WHERE r.type='MENTIONS' "
            "RETURN r.value_present",
            {"pid": property_id},
        )
    ]


def test_value_stated_in_prose_sets_value_present_true() -> None:
    store = _ingest(
        "Электроэкстракция никеля исследована. Скорость циркуляции католита "
        "составила 0.2 м/с в оптимальном режиме.",
        "vp_true",
    )
    try:
        flags = _mention_value_present(store, FLOW_VELOCITY)
        assert flags and all(f is True for f in flags)
    finally:
        store.close()


def test_property_named_without_value_sets_value_present_false() -> None:
    store = _ingest(
        "Электроэкстракция никеля исследована. Скорость циркуляции католита "
        "в данной кампании не измеряли; запланировано в будущей работе.",
        "vp_false",
    )
    try:
        flags = _mention_value_present(store, FLOW_VELOCITY)
        assert flags and all(f is False for f in flags)
    finally:
        store.close()


def test_material_mentions_carry_no_value_present() -> None:
    # Only Property MENTIONS edges get the flag; the material edge stays unflagged.
    store = _ingest(
        "Скорость циркуляции католита составила 0.2 м/с при электроэкстракции никеля.",
        "vp_mat",
    )
    try:
        mat_flags = _mention_value_present(store, NICKEL)
        assert mat_flags == [] or all(f is None for f in mat_flags)
    finally:
        store.close()


def test_reingest_updates_value_present_idempotently() -> None:
    # Store-level MERGE parity: a later write flips value_present False -> True on
    # the *same* edge (one edge, last write wins), mirroring Neo4j SET r += props.
    store = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    try:
        store.upsert_node("chunk1", "Chunk", text="t")
        store.upsert_node(FLOW_VELOCITY, "Property", property_name="flow_velocity")
        store.upsert_edge("chunk1", FLOW_VELOCITY, "MENTIONS", value_present=False)
        assert _mention_value_present(store, FLOW_VELOCITY) == [False]
        store.upsert_edge("chunk1", FLOW_VELOCITY, "MENTIONS", value_present=True)
        flags = _mention_value_present(store, FLOW_VELOCITY)
        assert flags == [True]  # updated in place, not duplicated
    finally:
        store.close()
