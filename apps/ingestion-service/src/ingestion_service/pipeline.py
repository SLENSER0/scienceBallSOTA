"""Ingestion pipeline (§5/§6/§9): parse → chunk → extract → evidence-first upsert.

Populates the Kuzu graph from the real corpus. Rule extraction runs on every
chunk (free); LLM extraction enriches up to ``llm_max_chunks`` chunks per doc.
Idempotent + deduped by document file hash.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ingestion_service.chunker import chunk_pages
from ingestion_service.parsers import ParsedDoc
from kg_common import evidence_id, get_logger, make_id
from kg_common.storage.base import CoverageEvent, MetaStore
from kg_extractors.composition_extractor import extract_compositions
from kg_extractors.processing_extractor import extract_processing
from kg_extractors.rule_extractor import extract_rules
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.extraction import DocumentExtraction
from kg_schema.taxonomy import load_taxonomy

_log = get_logger("ingest")
SCHEMA_VERSION = "0.1.0"

# Entity target types whose per-chunk coverage we log for absence-confidence (§25.5).
_COVERAGE_ENTITY_TYPES = ("Material", "TechnologySolution", "ProcessingRegime", "Property")

_STRENGTH = {
    "article": "peer_reviewed",
    "review": "peer_reviewed",
    "patent": "patent",
    "internal_report": "internal_report",
    "thesis": "peer_reviewed",
    "standard": "standard",
    "presentation": "expert_comment",
    "conference": "peer_reviewed",
}


@dataclass
class IngestStats:
    docs: int = 0
    skipped: int = 0
    chunks: int = 0
    entities: int = 0
    measurements: int = 0
    evidence: int = 0
    errors: int = 0
    llm_chunks: int = 0
    by_label: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "by_label"}
        d["by_label"] = dict(self.by_label)
        return d


def _practice_type(country: str | None) -> str:
    if not country:
        return "unknown"
    entry = load_taxonomy().by_id(country)
    return entry.practice_type if entry and entry.practice_type else "unknown"


class IngestionPipeline:
    def __init__(
        self,
        store: KuzuGraphStore,
        *,
        use_llm: bool = False,
        llm_max_chunks: int = 0,
        metastore: MetaStore | None = None,
    ) -> None:
        self.store = store
        self.use_llm = use_llm
        self.llm_max_chunks = llm_max_chunks
        # Optional coverage telemetry sink (§25.5). None → no logging (default, hot path unchanged).
        self.metastore = metastore
        self.tax = load_taxonomy()
        self.run_id = make_id("ExtractorRun", f"ingest-{datetime.now(UTC).date()}")
        self._now = datetime.now(UTC).isoformat()
        self.stats = IngestStats()
        self._entity_cache: set[str] = set()
        self.store.upsert_node(
            self.run_id,
            "ExtractorRun",
            name="ingestion",
            created_at=self._now,
            schema_version=SCHEMA_VERSION,
        )

    def _prov(self, **extra: object) -> dict:
        return {
            "extractor_run_id": self.run_id,
            "schema_version": SCHEMA_VERSION,
            "created_at": self._now,
            **extra,
        }

    def _doc_exists(self, file_hash: str) -> bool:
        doc_id = make_id("Document", file_hash)
        return self.store.get_node(doc_id) is not None

    def _upsert_entity(self, canonical: str, node_type: str, surface: str) -> str | None:
        entry = self.tax.by_id(canonical)
        if entry:
            nid = entry.node_id
            # canonical entities have stable props — upsert the node only once per run
            if nid not in self._entity_cache:
                self.store.upsert_node(
                    nid,
                    entry.node_type,
                    name=entry.canonical_ru or entry.canonical_en,
                    canonical_name=entry.canonical_en,
                    domain=entry.domain,
                    material_class=entry.material_class,
                    practice_type=entry.practice_type,
                    aliases_text="|".join(entry.all_terms),
                    **self._prov(confidence=0.7),
                )
                self._entity_cache.add(nid)
                self.stats.by_label[entry.node_type] += 1
            return nid
        if node_type in {
            "Material",
            "TechnologySolution",
            "Equipment",
            "Property",
            "ProcessingRegime",
            "Person",
            "Lab",
            "Method",
        }:
            nid = make_id(node_type, surface)
            self.store.upsert_node(
                nid, node_type, name=surface, canonical_name=surface, **self._prov(confidence=0.5)
            )
            self.stats.by_label[node_type] += 1
            return nid
        return None

    def ingest(self, doc: ParsedDoc) -> dict:
        if self._doc_exists(doc.file_hash):
            self.stats.skipped += 1
            return {"status": "skipped", "title": doc.title}

        doc_id = make_id("Document", doc.file_hash)
        chunks = chunk_pages(doc.pages)
        domains: Counter = Counter()
        llm_used = 0

        # first pass to guess domain
        for ch in chunks[:5]:
            for e in extract_rules(ch.text).entities:
                entry = self.tax.by_id(e.canonical_name or "")
                if entry and entry.domain:
                    domains[entry.domain] += 1
        top_domain = domains.most_common(1)[0][0] if domains else None

        self.store.upsert_node(
            doc_id,
            "Document",
            name=doc.title,
            canonical_name=doc.title,
            doc_type=doc.doc_type,
            lang=doc.lang,
            country=doc.country,
            year=doc.year,
            practice_type=_practice_type(doc.country),
            evidence_strength=_STRENGTH.get(doc.doc_type, "unverified"),
            domain=top_domain,
            **self._prov(source_type="metadata"),
        )
        self.store.upsert_node(  # also a Paper-like source node for citations
            make_id("Paper", doc.file_hash),
            "Paper",
            name=doc.title,
            year=doc.year,
            practice_type=_practice_type(doc.country),
            country=doc.country,
            evidence_strength=_STRENGTH.get(doc.doc_type, "unverified"),
            **self._prov(),
        )
        self.stats.docs += 1
        self.stats.by_label["Document"] += 1

        # batch all of a document's writes into one Kuzu transaction (faster bulk load)
        with self.store.batch():
            for ch in chunks:
                chunk_id = make_id("Chunk", f"{doc_id}:{ch.index}")
                self.store.upsert_node(
                    chunk_id,
                    "Chunk",
                    text=ch.text[:2000],
                    page=ch.page,
                    doc_id=doc_id,
                    **self._prov(),
                )
                self.store.upsert_edge(doc_id, chunk_id, "HAS_CHUNK", **self._prov())
                self.stats.chunks += 1

                ex = extract_rules(ch.text)
                if self.use_llm and llm_used < self.llm_max_chunks and len(ch.text) > 200:
                    from kg_extractors.llm_extractor import extract_llm

                    merged = extract_llm(ch.text)
                    ex = _merge(ex, merged)
                    llm_used += 1
                    self.stats.llm_chunks += 1

                self._apply_extraction(ex, doc_id, chunk_id, ch.page, ch.text)

        return {"status": "ok", "title": doc.title, "chunks": len(chunks)}

    def _log_coverage(self, ex: DocumentExtraction, doc_id: str, chunk_id: str) -> None:
        """Record which target types the extractor looked for + found in this chunk (§25.5)."""
        if self.metastore is None:
            return
        extractor = "rule+llm" if self.use_llm else "rule"
        counts: dict[str, int] = {"Measurement": len(ex.measurements)}
        for e in ex.entities:
            if e.entity_type in _COVERAGE_ENTITY_TYPES:
                counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
        for target in (*_COVERAGE_ENTITY_TYPES, "Measurement"):
            self.metastore.log_coverage(
                CoverageEvent(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    extractor=extractor,
                    target_type=target,
                    attempted=True,
                    found_count=counts.get(target, 0),
                    run_id=self.run_id,
                )
            )

    def _apply_extraction(
        self, ex: DocumentExtraction, doc_id: str, chunk_id: str, page: int, text: str = ""
    ) -> None:
        self._log_coverage(ex, doc_id, chunk_id)
        material_id: str | None = None
        for e in ex.entities:
            nid = self._upsert_entity(e.canonical_name or e.text, e.entity_type, e.text)
            if nid:
                self.store.upsert_edge(
                    chunk_id, nid, "MENTIONS", **self._prov(confidence=e.confidence)
                )
                self.stats.entities += 1
                if e.entity_type == "Material" and material_id is None:
                    material_id = nid

        for i, m in enumerate(ex.measurements):
            span = (m.evidence_text or m.value_raw or "")[:400]
            if not span:
                continue
            ev_id = evidence_id(doc_id, f"{chunk_id}:{i}:{span[:40]}", self.run_id)
            self.store.upsert_node(
                ev_id,
                "Evidence",
                text=span,
                doc_id=doc_id,
                page=page,
                source_type="paragraph",
                confidence=m.confidence,
                **self._prov(),
            )
            self.store.upsert_edge(ev_id, chunk_id, "FROM_CHUNK", **self._prov())
            self.stats.evidence += 1

            meas_id = make_id("Measurement", f"{doc_id}:{chunk_id}:m{i}")
            norm = None
            if m.value is not None and m.unit:
                from kg_extractors.units import to_canonical

                norm = to_canonical(m.value, m.unit)
            self.store.upsert_node(
                meas_id,
                "Measurement",
                name=m.property,
                property_name=m.property,
                value_normalized=(norm.value if norm else m.value),
                normalized_unit=(norm.unit if norm else m.unit),
                value_raw=m.value_raw,
                unit=m.unit,
                **self._prov(confidence=m.confidence),
            )
            self.store.upsert_edge(
                meas_id,
                ev_id,
                "SUPPORTED_BY",
                **self._prov(confidence=m.confidence, evidence_ids=[ev_id]),
            )
            mat = m.material and self._upsert_entity(m.material, "Material", m.material)
            if mat or material_id:
                self.store.upsert_edge(
                    meas_id,
                    mat or material_id,
                    "ABOUT_MATERIAL",
                    **self._prov(confidence=m.confidence),
                )
            self.stats.measurements += 1

        if text:
            self._apply_composition(text, chunk_id, material_id)
            self._apply_processing(text, chunk_id)

    def _apply_composition(self, text: str, chunk_id: str, material_id: str | None) -> None:
        """Materialize Composition→CONTAINS_ELEMENT→ChemicalElement from prose (§6.4)."""
        for cm in extract_compositions(text):
            comp_id = make_id("Composition", f"{chunk_id}:{'-'.join(cm.element_symbols())}")
            self.store.upsert_node(
                comp_id, "Composition", name=cm.text, base_element=cm.base_element or "",
                **self._prov(source_type="paragraph"),
            )
            if material_id:
                self.store.upsert_edge(material_id, comp_id, "HAS_COMPOSITION", **self._prov())
            for sym, frac in cm.elements.items():
                el_id = make_id("ChemicalElement", sym)
                self.store.upsert_node(el_id, "ChemicalElement", name=sym, symbol=sym)
                self.store.upsert_edge(
                    comp_id, el_id, "CONTAINS_ELEMENT",
                    **self._prov(fraction=frac if frac is not None else -1.0),
                )

    def _apply_processing(self, text: str, chunk_id: str) -> None:
        """Materialize ProcessingRegime→HAS_PARAMETER→Parameter from prose (§6.5)."""
        for pm in extract_processing(text):
            reg_id = make_id("ProcessingRegime", pm.method)
            self.store.upsert_node(
                reg_id, "ProcessingRegime", name=pm.method, **self._prov(source_type="paragraph")
            )
            self.store.upsert_edge(chunk_id, reg_id, "MENTIONS", **self._prov())
            for pname, pval in pm.parameters.items():
                par_id = make_id("Parameter", f"{pm.method}:{pname}:{pval}")
                self.store.upsert_node(
                    par_id, "Parameter", name=pname, value_normalized=pval, **self._prov()
                )
                self.store.upsert_edge(reg_id, par_id, "HAS_PARAMETER", **self._prov())
            self.stats.by_label["Measurement"] += 1


def _merge(a: DocumentExtraction, b: DocumentExtraction) -> DocumentExtraction:
    a.entities.extend(b.entities)
    a.measurements.extend(b.measurements)
    a.relations.extend(b.relations)
    a.claims.extend(b.claims)
    return a
