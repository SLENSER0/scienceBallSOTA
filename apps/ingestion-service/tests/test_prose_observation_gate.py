"""[DE] N3 — prose numeric values are review-gated when opted in (§33/N3, D16).

Audit finding: the pipeline materialises prose numerics as Measurements whose
``review_needed`` is set ONLY by physical-range validation — a prose value in range
auto-commits. The opt-in ``prose_observation_extraction`` flag closes that: with it
on, any prose numeric measurement is review-gated (never an accepted fact without a
human). Flag off = legacy; the change is idempotent under re-ingest.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ingestion_service.parsers import ParsedDoc
from ingestion_service.pipeline import IngestionPipeline

from kg_retrievers.graph_store import KuzuGraphStore

# in-range current-density prose (would NOT be flagged by range validation alone)
SAMPLE = (
    "Электроэкстракция никеля проводилась при плотности тока 250 А/м². "
    "Скорость циркуляции католита составила 0.2 м/с."
)


def _ingest(file_hash: str, *, gate: bool | None) -> KuzuGraphStore:
    store = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    doc = ParsedDoc(
        path="x.txt",
        title="N3",
        doc_type="article",
        file_hash=file_hash,
        lang="ru",
        pages=[(1, SAMPLE)],
        country="russia",
        year=2023,
    )
    IngestionPipeline(store, prose_observation_extraction=gate).ingest(doc)
    return store


def _numeric_measurements(store: KuzuGraphStore) -> list[dict]:
    rows = store.rows("MATCH (m:Node {label:'Measurement'}) RETURN m.id")
    nodes = [store.get_node(r[0]) or {} for r in rows]
    return [n for n in nodes if n.get("value_normalized") is not None]


def test_flag_on_review_gates_in_range_prose_numeric() -> None:
    store = _ingest("n3_on", gate=True)
    try:
        meas = _numeric_measurements(store)
        assert meas and all(m.get("review_needed") for m in meas)
    finally:
        store.close()


def test_flag_off_leaves_in_range_prose_unflagged() -> None:
    store = _ingest("n3_off", gate=False)
    try:
        meas = _numeric_measurements(store)
        # legacy: an in-range value is not review-gated by provenance
        assert meas and not all(m.get("review_needed") for m in meas)
    finally:
        store.close()
