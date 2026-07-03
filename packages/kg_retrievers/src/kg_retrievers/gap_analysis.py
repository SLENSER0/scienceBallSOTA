"""Gap analysis + contradiction detection (§15 / §25).

Scans the graph for missing values, low coverage, orphan entities, missing units
and *contradictory measurements* (same property on the same subject with
divergent values), materializing Gap / Contradiction nodes with GapScanRun
provenance. Idempotent (deterministic ids).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from kg_common import get_logger, make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.enums import GapType

_log = get_logger("gap_analysis")
SCHEMA_VERSION = "0.1.0"
DIVERGENCE = 0.30  # relative difference to flag a contradiction


@dataclass
class ScanResult:
    run_id: str
    gaps_created: int = 0
    contradictions_created: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "gaps": self.gaps_created,
            "contradictions": self.contradictions_created,
            "by_type": self.by_type,
        }


class GapScanner:
    def __init__(self, store: KuzuGraphStore) -> None:
        self.store = store
        self.run_id = make_id("GapScanRun", datetime.now(UTC).isoformat())
        self._now = datetime.now(UTC).isoformat()
        self.store.upsert_node(
            self.run_id,
            "GapScanRun",
            name="gap_scan",
            created_at=self._now,
            schema_version=SCHEMA_VERSION,
        )

    def _prov(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": self._now,
            "extractor_run_id": self.run_id,
            "review_status": "pending",
            "verified": False,
        }

    def _gap(
        self, res: ScanResult, key: str, gtype: GapType, name: str, about: str | None = None
    ) -> None:
        gid = make_id("Gap", f"{gtype}:{key}")
        if self.store.get_node(gid):
            return
        self.store.upsert_node(gid, "Gap", name=name, gap_type=str(gtype), **self._prov())
        self.store.upsert_edge(gid, self.run_id, "DETECTED_BY", **self._prov())
        if about:
            self.store.upsert_edge(gid, about, "ABOUT", **self._prov())
        res.gaps_created += 1
        res.by_type[str(gtype)] = res.by_type.get(str(gtype), 0) + 1

    def scan(self) -> ScanResult:
        res = ScanResult(run_id=self.run_id)
        self._scan_missing_unit(res)
        self._scan_missing_source_span(res)
        self._scan_low_confidence_er(res)
        self._scan_orphans(res)
        self._scan_low_coverage(res)
        self._scan_missing_geography(res)
        self._scan_contradictions(res)
        _log.info("gap_scan.done", **res.as_dict())
        return res

    def _scan_missing_source_span(self, res: ScanResult) -> None:
        # A factual node backed by Evidence that carries no quotable text span —
        # the claim exists but can't be verified against a source (§15.3).
        rows = self.store.rows(
            "MATCH (f:Node)-[:Rel]->(e:Node) "
            "WHERE f.label IN ['Measurement','Claim','Finding','KnowledgeClaim'] "
            "AND e.label='Evidence' AND (e.text IS NULL OR e.text='') "
            "RETURN DISTINCT f.id, coalesce(f.name,'') LIMIT 500"
        )
        for fid, name in rows:
            self._gap(
                res,
                fid,
                GapType.MISSING_SOURCE_SPAN,
                f"Утверждение без цитаты-источника: {name}",
                about=fid,
            )

    def _scan_low_confidence_er(self, res: ScanResult) -> None:
        # Ad-hoc surface-form entities resolved with low confidence — candidates
        # for entity-resolution review, surfaced as a gap (§15.3 / §8.7).
        rows = self.store.rows(
            "MATCH (n:Node) WHERE n.label IN "
            "['Material','TechnologySolution','Equipment','Person','Lab','Method'] "
            "AND n.confidence IS NOT NULL AND n.confidence < 0.6 "
            "RETURN n.id, coalesce(n.name,'') LIMIT 500"
        )
        for nid, name in rows:
            self._gap(
                res,
                nid,
                GapType.LOW_CONFIDENCE_ENTITY_RESOLUTION,
                f"Ненадёжное разрешение сущности: {name}",
                about=nid,
            )

    def _scan_missing_unit(self, res: ScanResult) -> None:
        rows = self.store.rows(
            "MATCH (m:Node) WHERE m.label='Measurement' AND m.value_normalized IS NOT NULL "
            "AND m.normalized_unit IS NULL RETURN m.id LIMIT 500"
        )
        for (mid,) in rows:
            self._gap(res, mid, GapType.MISSING_UNIT, "Измерение без единицы измерения", about=mid)

    def _scan_orphans(self, res: ScanResult) -> None:
        rows = self.store.rows(
            "MATCH (n:Node) WHERE n.label IN ['Material','TechnologySolution','Equipment'] "
            "AND NOT (n)-[:Rel]-() RETURN n.id, n.name LIMIT 300"
        )
        for nid, name in rows:
            self._gap(res, nid, GapType.ORPHAN_ENTITY, f"Изолированная сущность: {name}", about=nid)

    def _scan_low_coverage(self, res: ScanResult) -> None:
        rows = self.store.rows(
            "MATCH (m:Node) WHERE m.label='Material' "
            "OPTIONAL MATCH (m)-[:Rel]-(e:Node) WHERE e.label IN ['Evidence','Measurement'] "
            "RETURN m.id, m.name, count(e) LIMIT 500"
        )
        for mid, name, cnt in rows:
            if cnt < 1:
                self._gap(
                    res,
                    mid,
                    GapType.LOW_COVERAGE_MATERIAL,
                    f"Низкое покрытие материала: {name}",
                    about=mid,
                )

    def _scan_missing_geography(self, res: ScanResult) -> None:
        rows = self.store.rows(
            "MATCH (t:Node) WHERE t.label='TechnologySolution' AND t.practice_type IS NULL "
            "RETURN t.id, t.name LIMIT 300"
        )
        for tid, name in rows:
            self._gap(
                res,
                tid,
                GapType.MISSING_GEOGRAPHY,
                f"Нет географии/практики для решения: {name}",
                about=tid,
            )

    def _scan_contradictions(self, res: ScanResult) -> None:
        # Measurements of the same property about the same subject with divergent values.
        rows = self.store.rows(
            "MATCH (m1:Node)-[:Rel]-(subj:Node)-[:Rel]-(m2:Node) "
            "WHERE m1.label='Measurement' AND m2.label='Measurement' AND m1.id < m2.id "
            "AND m1.property_name = m2.property_name "
            "AND m1.value_normalized IS NOT NULL AND m2.value_normalized IS NOT NULL "
            "AND m1.normalized_unit = m2.normalized_unit "
            "RETURN m1.id, m1.value_normalized, m2.id, m2.value_normalized, "
            "m1.property_name, subj.name, subj.id LIMIT 400"
        )
        seen: set[tuple[str, str]] = set()
        for m1, v1, m2, v2, prop, subj_name, subj_id in rows:
            key = (m1, m2)
            if key in seen or v1 is None or v2 is None:
                continue
            seen.add(key)
            hi = max(abs(v1), abs(v2)) or 1.0
            if abs(v1 - v2) / hi < DIVERGENCE:
                continue
            cid = make_id("Contradiction", f"{prop}:{m1}:{m2}")
            if self.store.get_node(cid):
                continue
            self.store.upsert_node(
                cid,
                "Contradiction",
                name=f"Противоречие по «{prop}» ({v1} vs {v2}) — {subj_name}",
                gap_type=str(GapType.CONTRADICTORY_MEASUREMENTS),
                **self._prov(),
            )
            self.store.upsert_edge(m1, m2, "CONTRADICTS", **self._prov())
            self.store.upsert_edge(cid, self.run_id, "DETECTED_BY", **self._prov())
            # Link the Contradiction to its subject + measurements so the query
            # pipeline can reach it (finding gap_analysis.py:153).
            self.store.upsert_edge(cid, subj_id, "ABOUT", **self._prov())
            self.store.upsert_edge(cid, m1, "ABOUT", **self._prov())
            self.store.upsert_edge(cid, m2, "ABOUT", **self._prov())
            res.contradictions_created += 1
