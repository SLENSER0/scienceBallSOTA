"""Chunker + rule extraction + pipeline smoke (§5/§6)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ingestion_service.chunker import chunk_pages
from ingestion_service.parsers import ParsedDoc
from ingestion_service.pipeline import IngestionPipeline

from kg_extractors.rule_extractor import extract_rules
from kg_retrievers.graph_store import KuzuGraphStore

SAMPLE = (
    "Электроэкстракция никеля из сульфатного электролита проводилась при плотности "
    "тока 250 А/м². Оптимальная скорость циркуляции католита составила 0.2 м/с. "
    "Мокрая сероочистка обеспечивает удаление SO2 на уровне 95%."
)


def test_chunker() -> None:
    chunks = chunk_pages([(1, "a" * 3000)], size=1000, overlap=100)
    assert len(chunks) >= 3
    assert all(c.page == 1 for c in chunks)


def test_rule_extractor_finds_domain_entities() -> None:
    ex = extract_rules(SAMPLE)
    ids = {e.canonical_name for e in ex.entities}
    assert "nickel" in ids and "electrowinning" in ids
    # current density 250 A/m2 captured as a measurement with a unit
    units = {m.unit for m in ex.measurements}
    assert any(u and ("A/m" in u or "m/s" in u or "percent" in u) for u in units)
    # every extraction carries an evidence span
    assert all(e.evidence_text for e in ex.entities)
    assert all(m.evidence_text for m in ex.measurements)


def test_pipeline_upserts_evidence_first() -> None:
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    doc = ParsedDoc(
        path="x.txt",
        title="Тест",
        doc_type="article",
        file_hash="hash1",
        lang="ru",
        pages=[(1, SAMPLE)],
        country="russia",
        year=2023,
    )
    pipe = IngestionPipeline(store)
    res = pipe.ingest(doc)
    assert res["status"] == "ok"
    # idempotent: same hash → skipped
    assert pipe.ingest(doc)["status"] == "skipped"
    # every ingested measurement is evidence-backed (SUPPORTED_BY -> Evidence)
    orphan = store.rows(
        "MATCH (m:Node) WHERE m.label='Measurement' AND NOT (m)-[:Rel]->(:Node {label:'Evidence'}) "
        "RETURN count(m)"
    )
    assert orphan[0][0] == 0
    assert store.counts()["nodes"] > 5
    store.close()


def test_pipeline_logs_coverage_to_metastore() -> None:
    # §25.5: when a MetaStore is supplied, per-chunk coverage is logged so the
    # absence-confidence layer can tell a true gap from mere non-extraction.
    from kg_common.storage import SqlMetaStore

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    meta = SqlMetaStore("sqlite:///:memory:")
    meta.migrate()
    doc = ParsedDoc(
        path="x.txt",
        title="Покрытие",
        doc_type="article",
        file_hash="cov1",
        lang="ru",
        pages=[(1, SAMPLE)],
        country="russia",
        year=2023,
    )
    try:
        IngestionPipeline(store, metastore=meta).ingest(doc)
        stats = {s.target_type: s for s in meta.coverage_stats()}
        assert "Measurement" in stats and stats["Measurement"].n_attempts >= 1
        # SAMPLE carries a current-density measurement → ≥1 chunk found one
        assert stats["Measurement"].n_found >= 1
        # entity target types are logged as attempted too
        assert "Material" in stats
    finally:
        store.close()


def test_pipeline_materializes_composition_and_processing() -> None:
    # §6.4/§6.5 integration: prose with an alloy + a process yields Composition/
    # ChemicalElement and ProcessingRegime/Parameter nodes.
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    text = (
        "Сплав Al-4Cu-1Mg подвергали старению. Электроэкстракция никеля велась "
        "при 60 °C, плотность тока 250 А/м²."
    )
    doc = ParsedDoc(path="x.txt", title="Состав", doc_type="article", file_hash="cp1",
                    lang="ru", pages=[(1, text)], country="russia", year=2023)
    try:
        IngestionPipeline(store).ingest(doc)
        by = store.counts_by_label()
        assert by.get("ChemicalElement", 0) >= 2
        assert by.get("Composition", 0) >= 1
        assert by.get("ProcessingRegime", 0) >= 1
        assert by.get("Parameter", 0) >= 1
        # CONTAINS_ELEMENT wiring exists
        n = store.rows(
            "MATCH (c:Node {label:'Composition'})-[:Rel {type:'CONTAINS_ELEMENT'}]->"
            "(e:Node {label:'ChemicalElement'}) RETURN count(*)"
        )
        assert n[0][0] >= 2
    finally:
        store.close()


def test_section_aware_chunking() -> None:
    from ingestion_service.chunker import chunk_pages

    text = (
        "## Введение\n"
        "Работа посвящена электроэкстракции никеля. Метод широко применяется.\n"
        "## Методы\n"
        "Электролиз вели при 60 C. Плотность тока составляла 250 единиц.\n"
    )
    chunks = chunk_pages([(1, text)], size=200, overlap=20)
    assert chunks
    paths = {tuple(c.section_path) for c in chunks}
    assert ("Введение",) in paths and ("Методы",) in paths
    # no chunk mixes the two sections' bodies
    intro = next(c for c in chunks if c.section_path == ["Введение"])
    assert "Электролиз" not in intro.text


def test_pipeline_registers_source() -> None:
    # §5.4: with a SourceRegistry, ingesting a doc records its provenance.
    from kg_common.storage.source_registry import SourceRegistry

    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    reg = SourceRegistry("sqlite:///:memory:")
    reg.migrate()
    doc = ParsedDoc(path="/data/a.pdf", title="Src", doc_type="article", file_hash="sh1",
                    lang="ru", pages=[(1, SAMPLE)], country="russia", year=2023)
    try:
        IngestionPipeline(store, source_registry=reg).ingest(doc)
        s = reg.by_hash("sh1")
        assert s is not None and s.status == "ingested" and s.title == "Src"
        assert reg.exists("sh1")
    finally:
        store.close()
