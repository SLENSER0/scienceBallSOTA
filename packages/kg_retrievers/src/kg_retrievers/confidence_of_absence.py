"""Confidence-of-absence for reported knowledge gaps (§25.3–25.5, §25.9).

A gap of the form "no data for material × process × property" is only meaningful
if we can say *how likely it is that the absence is real* rather than an artefact
of imperfect extraction. This module qualifies each empty coverage cell with

    P(absence is real | we observed no evidence)

computed from a per-property / per-entity-type *extractor recall* estimate.

Intuition (a one-line Bayesian update with prior ``p0 = P(the datum exists)``):
- if we found **0** evidence and recall is **high**, our miss is unlikely, so the
  absence is probably real → high ``confidence_of_absence``;
- if recall is **low**, finding nothing tells us almost nothing → ``"unknown"``.

    posterior = (1 - p0) / ((1 - p0) + p0 * (1 - recall))

With the default prior ``p0 = 0.5`` this collapses to ``1 / (2 - recall)``: recall
1.0 → 1.0 (certain the gap is real), recall 0.0 → 0.5 (back to the prior).

``AbsenceAnalyzer.scan_absence`` materialises the qualified gaps as ``Gap`` nodes
carrying an ``absence_confidence`` field, so the query pipeline can distinguish a
"we are confident nobody has studied this" gap from a "our extractor may have
missed it" non-signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from kg_common import get_logger, make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.enums import GapType

_log = get_logger("confidence_of_absence")

SCHEMA_VERSION = "0.1.0"

# Recall model -------------------------------------------------------------
DEFAULT_RECALL = 0.7
# Below this recall a null observation is uninformative → we report "unknown".
UNKNOWN_RECALL_THRESHOLD = 0.4
# posterior at/above which we call the absence a real, qualified gap.
CONFIDENT_THRESHOLD = 0.66
# Prior P(the datum exists in the corpus) before we look.
DEFAULT_PRIOR_EXISTS = 0.5
# How many hops out from a subject a Measurement still counts as "covering" it.
DEFAULT_COVERAGE_DEPTH = 2

# Cell status labels.
COVERED = "covered"
CONFIDENT_ABSENCE = "confident_absence"
POSSIBLE_ABSENCE = "possible_absence"
UNKNOWN = "unknown"

# Properties we probe for by default when scanning materials for real absences.
# (Kept independent of what happens to be in the graph so a domain-wide absence
# — e.g. nobody ever measured ``recovery`` for a material — is detectable.)
DEFAULT_PROPERTIES: tuple[str, ...] = (
    "recovery",
    "concentration",
    "current_density",
    "flow_velocity",
    "removal_efficiency",
    "energy_consumption",
    "capex",
    "opex",
)


@dataclass
class ExtractorRecall:
    """Estimated recall of the extractor, keyed by property then entity type.

    ``for_property`` resolves most-specific-first: an explicit per-property recall
    wins over a per-entity-type recall, which wins over ``default`` (0.7).
    """

    default: float = DEFAULT_RECALL
    per_property: dict[str, float] = field(default_factory=dict)
    per_entity_type: dict[str, float] = field(default_factory=dict)

    def for_property(self, property_name: str, entity_type: str | None = None) -> float:
        if property_name in self.per_property:
            return _clamp01(self.per_property[property_name])
        if entity_type and entity_type in self.per_entity_type:
            return _clamp01(self.per_entity_type[entity_type])
        return _clamp01(self.default)


@dataclass
class CoverageCell:
    """One (subject, property) coverage cell qualified with confidence-of-absence."""

    material_id: str
    material_name: str
    property_name: str
    evidence_count: int
    recall: float
    confidence_of_absence: float | str  # float in [0,1], or "unknown"
    status: str  # COVERED | CONFIDENT_ABSENCE | POSSIBLE_ABSENCE | UNKNOWN
    gap_id: str | None = None

    @property
    def is_qualified_absence(self) -> bool:
        return self.status == CONFIDENT_ABSENCE

    def as_dict(self) -> dict:
        return {
            "material_id": self.material_id,
            "material_name": self.material_name,
            "property_name": self.property_name,
            "evidence_count": self.evidence_count,
            "recall": self.recall,
            "confidence_of_absence": self.confidence_of_absence,
            "status": self.status,
            "gap_id": self.gap_id,
        }


def _clamp01(x: float) -> float:
    return max(0.0, min(float(x), 1.0))


class AbsenceAnalyzer:
    """Qualifies empty coverage cells with P(absence is real | extractor recall)."""

    def __init__(
        self,
        store: KuzuGraphStore,
        *,
        recall: ExtractorRecall | None = None,
        prior_exists: float = DEFAULT_PRIOR_EXISTS,
        default_properties: list[str] | None = None,
        coverage_depth: int = DEFAULT_COVERAGE_DEPTH,
    ) -> None:
        self.store = store
        self.recall = recall or ExtractorRecall()
        # keep the prior strictly inside (0, 1) so the posterior is always defined
        self.prior_exists = max(0.01, min(float(prior_exists), 0.99))
        self.default_properties: list[str] = list(default_properties or DEFAULT_PROPERTIES)
        self.coverage_depth = max(1, min(int(coverage_depth), 3))
        self._now = datetime.now(UTC).isoformat()
        self.run_id = make_id("GapScanRun", f"absence:{self._now}")
        self._run_created = False

    # -- public API ------------------------------------------------------
    def coverage_matrix(self, materials: list[str], properties: list[str]) -> list[CoverageCell]:
        """Coverage + confidence-of-absence for every (material, property) pair.

        ``materials`` may be node ids or names/canonical names — each is resolved
        to a graph node. Cells with evidence are ``COVERED`` (confidence 0.0);
        empty cells carry a recall-adjusted ``confidence_of_absence`` float, or the
        string ``"unknown"`` when recall is too low to conclude anything (§25.3–25.4).
        """
        cells: list[CoverageCell] = []
        for material in materials:
            mid, mname, mlabel = self._resolve(material)
            for prop in properties:
                cells.append(self._cell(mid, mname, mlabel, prop))
        return cells

    def scan_absence(
        self,
        domain: str | None = None,
        *,
        properties: list[str] | None = None,
        min_confidence: float = CONFIDENT_THRESHOLD,
        materialize: bool = True,
    ) -> list[CoverageCell]:
        """Scan materials (optionally within ``domain``) for real, qualified gaps.

        Returns the cells whose absence is confident enough (posterior ≥
        ``min_confidence``). When ``materialize`` is set, each is stored as a ``Gap``
        node with an ``absence_confidence`` field and an ``ABOUT`` edge to the
        subject (§25.5, §25.9).
        """
        props = list(properties or self.default_properties)
        qualified: list[CoverageCell] = []
        for mid, mname, mlabel in self._candidate_materials(domain):
            for prop in props:
                cell = self._cell(mid, mname, mlabel, prop)
                if cell.status != CONFIDENT_ABSENCE:
                    continue
                if not isinstance(cell.confidence_of_absence, float):
                    continue
                if cell.confidence_of_absence < min_confidence:
                    continue
                if materialize:
                    self._materialize_gap(cell)
                qualified.append(cell)
        _log.info(
            "absence_scan.done",
            domain=domain or "*",
            qualified=len(qualified),
            run_id=self.run_id,
        )
        return qualified

    # -- core computation ------------------------------------------------
    def _cell(self, mid: str, mname: str, mlabel: str, prop: str) -> CoverageCell:
        count = self._evidence_count(mid, prop)
        recall = self.recall.for_property(prop, mlabel)
        conf, status = self._absence_confidence(count, recall)
        return CoverageCell(mid, mname, prop, count, recall, conf, status)

    def _absence_confidence(self, evidence_count: int, recall: float) -> tuple[float | str, str]:
        """P(absence is real | 0 evidence) via a one-step Bayesian update on recall."""
        recall = _clamp01(recall)
        if evidence_count > 0:
            return 0.0, COVERED
        if recall < UNKNOWN_RECALL_THRESHOLD:
            # a null observation from a low-recall extractor is uninformative
            return UNKNOWN, UNKNOWN
        p_exists = self.prior_exists
        p_absent = 1.0 - p_exists
        posterior = p_absent / (p_absent + p_exists * (1.0 - recall))
        posterior = round(posterior, 4)
        status = CONFIDENT_ABSENCE if posterior >= CONFIDENT_THRESHOLD else POSSIBLE_ABSENCE
        return posterior, status

    def _evidence_count(self, subject_id: str, property_name: str) -> int:
        """Distinct Measurements of ``property_name`` within N hops of the subject."""
        rows = self.store.rows(
            f"MATCH (s:Node {{id:$sid}})-[:Rel*1..{self.coverage_depth}]-(meas:Node) "
            "WHERE meas.label='Measurement' AND meas.property_name=$prop "
            "RETURN DISTINCT meas.id",
            {"sid": subject_id, "prop": property_name},
        )
        return len(rows)

    # -- resolution / candidates ----------------------------------------
    def _resolve(self, material: str) -> tuple[str, str, str]:
        nd = self.store.get_node(material)
        if nd:
            name = nd.get("name") or nd.get("canonical_name") or nd["id"]
            return nd["id"], name, nd.get("label", "Material")
        rows = self.store.rows(
            "MATCH (n:Node) WHERE lower(n.name)=lower($m) OR lower(n.canonical_name)=lower($m) "
            "RETURN n.id, n.name, n.label LIMIT 1",
            {"m": material},
        )
        if rows:
            r = rows[0]
            return r[0], r[1] or r[0], r[2] or "Material"
        return material, material, "Material"

    def _candidate_materials(self, domain: str | None) -> list[tuple[str, str, str]]:
        if domain:
            rows = self.store.rows(
                "MATCH (n:Node) WHERE n.label='Material' AND n.domain=$d "
                "RETURN n.id, n.name, n.label ORDER BY n.id",
                {"d": domain},
            )
        else:
            rows = self.store.rows(
                "MATCH (n:Node) WHERE n.label='Material' RETURN n.id, n.name, n.label ORDER BY n.id"
            )
        return [(r[0], r[1] or r[0], r[2] or "Material") for r in rows]

    # -- persistence -----------------------------------------------------
    def _prov(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": self._now,
            "extractor_run_id": self.run_id,
            "review_status": "pending",
            "verified": False,
        }

    def _ensure_run(self) -> None:
        if self._run_created:
            return
        self.store.upsert_node(
            self.run_id,
            "GapScanRun",
            name="absence_scan",
            created_at=self._now,
            schema_version=SCHEMA_VERSION,
        )
        self._run_created = True

    def _materialize_gap(self, cell: CoverageCell) -> str:
        """Upsert a qualified absence as a Gap node (idempotent by subject×property)."""
        self._ensure_run()
        gid = make_id("Gap", f"absence:{cell.material_id}:{cell.property_name}")
        conf = float(cell.confidence_of_absence)  # type: ignore[arg-type]
        self.store.upsert_node(
            gid,
            "Gap",
            name=(
                f"Нет данных: {cell.material_name} × {cell.property_name} "
                f"(P(отсутствие реально)={conf})"
            ),
            gap_type=str(GapType.MISSING_PROPERTY_VALUE),
            property_name=cell.property_name,
            absence_confidence=conf,
            **self._prov(),
        )
        self.store.upsert_edge(gid, cell.material_id, "ABOUT", **self._prov())
        self.store.upsert_edge(gid, self.run_id, "DETECTED_BY", **self._prov())
        cell.gap_id = gid
        return gid
