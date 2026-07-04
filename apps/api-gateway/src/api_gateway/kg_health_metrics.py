"""Live-graph data-quality metrics feeding the KG Health Score (§23.24).

:mod:`kg_eval.kg_health_score` folds a bag of *already-normalized* component
metrics (each ``0..1``) into a composite 0–100 verdict, and
:mod:`kg_eval.kg_health_slice_breakdown` scores the same bag *per slice* to
surface the graph's sickest areas. Both are pure scorers — they do not know how
to read a graph. This module is the missing adapter: it derives those raw
component metrics from the *live* graph store (Neo4j server profile / Kuzu),
then hands them to the existing scorers. Nothing here re-implements the scoring
math — it only counts nodes/edges and turns them into the five component ratios.

The five components (keys must match ``kg_eval.kg_health_score.DEFAULT_WEIGHTS``):

* ``evidence_coverage``  — claim-like nodes with evidence support / all claims.
* ``orphan_rate``        — disconnected nodes / all nodes (lower is better).
* ``duplicate_rate``     — entity nodes in a same-name cluster / all entities.
* ``contradiction_rate`` — claims touched by a contradiction / all claims.
* ``stale_rate``         — dated sources older than ``stale_years`` / all dated.

Metrics whose denominator is zero for a given node set are *omitted* rather than
forced to 0/1 — the scorer treats a scorecard as partial and normalises against
the weights that are actually present, so a slice with no papers is not punished
for having no ``stale_rate``.

Slices are computed along one dimension at a time (``domain`` / ``material`` /
``property`` / ``source_type``) so the dashboard can pick where the graph hurts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from kg_eval.kg_health_score import DEFAULT_WEIGHTS, kg_health_score
from kg_eval.kg_health_slice_breakdown import breakdown

# --- graph vocabulary -------------------------------------------------------
# Labels that carry a measured/asserted value — the denominator for evidence &
# contradiction coverage.
CLAIM_LABELS: frozenset[str] = frozenset({"Measurement", "TechnoEconomicIndicator"})
# Resolvable real-world entities — the denominator for duplicate rate. Excludes
# artefacts (Evidence, Contradiction, Gap, ExtractorRun) that legitimately repeat.
ENTITY_LABELS: frozenset[str] = frozenset(
    {
        "Material",
        "TechnologySolution",
        "Method",
        "Equipment",
        "ProcessingRegime",
        "Facility",
        "Lab",
        "Person",
        "ChemicalElement",
        "ApplicabilityCondition",
    }
)
# Bibliographic sources — the denominator for staleness (only ones with a year).
SOURCE_LABELS: frozenset[str] = frozenset({"Paper", "Document"})
# System/bookkeeping nodes excluded from the health census entirely.
SYSTEM_LABELS: frozenset[str] = frozenset({"ExtractorRun", "GapScanRun"})

_EVIDENCE_LABEL = "Evidence"
_CONTRADICTION_LABEL = "Contradiction"

# Per-metric acceptance thresholds compared against the *effective* (higher-is-
# better) value, so e.g. orphan_rate 0.30 → effective 0.70 must clear 0.70.
DEFAULT_THRESHOLDS: Mapping[str, float] = {
    "evidence_coverage": 0.55,
    "orphan_rate": 0.70,  # orphan_rate <= 0.30
    "duplicate_rate": 0.90,  # duplicate_rate <= 0.10
    "contradiction_rate": 0.80,  # contradiction_rate <= 0.20
    "stale_rate": 0.50,  # stale_rate <= 0.50
}

# Human-readable component labels for the dashboard (RU, matching the UI).
COMPONENT_LABELS: Mapping[str, str] = {
    "evidence_coverage": "Покрытие доказательствами",
    "orphan_rate": "Доля сирот",
    "duplicate_rate": "Доля дубликатов",
    "contradiction_rate": "Доля противоречий",
    "stale_rate": "Доля устаревших источников",
}

_DIMENSIONS: Mapping[str, str] = {
    "domain": "domain",
    "material": "material_class",
    "property": "property_name",
    "source_type": "source_type",
}


def _norm_name(raw: str | None) -> str:
    return (raw or "").strip().casefold()


@dataclass
class _NodeRec:
    """Per-node census row with the derived flags each metric needs."""

    node_id: str
    label: str
    degree: int = 0
    domain: str | None = None
    material_class: str | None = None
    property_name: str | None = None
    source_type: str | None = None
    year: int | None = None
    name: str = ""
    evidenced: bool = False
    contradicted: bool = False
    duplicate: bool = False

    @property
    def is_claim(self) -> bool:
        return self.label in CLAIM_LABELS

    @property
    def is_entity(self) -> bool:
        return self.label in ENTITY_LABELS

    @property
    def is_dated_source(self) -> bool:
        return self.label in SOURCE_LABELS and self.year is not None

    def slice_key(self, dimension: str) -> str | None:
        return getattr(self, _DIMENSIONS[dimension], None)


@dataclass
class _Bucket:
    """Running counts for one node set (whole graph or a single slice)."""

    size: int = 0
    orphans: int = 0
    entities: int = 0
    duplicates: int = 0
    claims: int = 0
    evidenced: int = 0
    contradicted: int = 0
    dated_sources: int = 0
    stale: int = 0
    labels: dict[str, int] = field(default_factory=dict)

    def add(self, rec: _NodeRec, *, stale_year_cutoff: int) -> None:
        self.size += 1
        self.labels[rec.label] = self.labels.get(rec.label, 0) + 1
        if rec.degree == 0:
            self.orphans += 1
        if rec.is_entity:
            self.entities += 1
            if rec.duplicate:
                self.duplicates += 1
        if rec.is_claim:
            self.claims += 1
            if rec.evidenced:
                self.evidenced += 1
            if rec.contradicted:
                self.contradicted += 1
        if rec.is_dated_source:
            self.dated_sources += 1
            if rec.year is not None and rec.year < stale_year_cutoff:
                self.stale += 1

    def metrics(self) -> dict[str, float]:
        """Component ratios; a metric is omitted when its denominator is 0."""
        out: dict[str, float] = {}
        if self.size:
            out["orphan_rate"] = self.orphans / self.size
        if self.entities:
            out["duplicate_rate"] = self.duplicates / self.entities
        if self.claims:
            out["evidence_coverage"] = self.evidenced / self.claims
            out["contradiction_rate"] = self.contradicted / self.claims
        if self.dated_sources:
            out["stale_rate"] = self.stale / self.dated_sources
        return out


def _to_int(raw: object) -> int | None:
    try:
        if raw is None:
            return None
        return int(raw)
    except (TypeError, ValueError):
        return None


def _load_nodes(store) -> dict[str, _NodeRec]:  # type: ignore[no-untyped-def]
    rows = store.rows(
        "MATCH (n:Node) RETURN n.id, coalesce(n.label,'Entity'), n.domain, "
        "n.material_class, n.property_name, n.source_type, n.year, "
        "coalesce(n.canonical_name, n.name, n.id)"
    )
    recs: dict[str, _NodeRec] = {}
    for nid, label, domain, material, prop, stype, year, name in rows:
        if not nid or label in SYSTEM_LABELS:
            continue
        recs[nid] = _NodeRec(
            node_id=nid,
            label=label or "Entity",
            domain=domain or None,
            material_class=material or None,
            property_name=prop or None,
            source_type=stype or None,
            year=_to_int(year),
            name=name or nid,
        )
    return recs


def _apply_edges(store, recs: dict[str, _NodeRec]) -> None:  # type: ignore[no-untyped-def]
    """Fold edges into degree + evidence/contradiction flags (§23.24 metrics)."""
    evidence_ids = {r.node_id for r in recs.values() if r.label == _EVIDENCE_LABEL}
    contradiction_ids = {r.node_id for r in recs.values() if r.label == _CONTRADICTION_LABEL}

    edge_rows = store.rows("MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id, r.type")
    for a, b, rtype in edge_rows:
        ra = recs.get(a)
        rb = recs.get(b)
        if ra is not None:
            ra.degree += 1
        if rb is not None:
            rb.degree += 1
        rt = (rtype or "").upper()

        # Evidence support: either an explicit SUPPORTED_BY edge, or adjacency to
        # an Evidence node (evidence attached on the far endpoint).
        if rt == "SUPPORTED_BY":
            if ra is not None:
                ra.evidenced = True
            if rb is not None:
                rb.evidenced = True
        if b in evidence_ids and ra is not None:
            ra.evidenced = True
        if a in evidence_ids and rb is not None:
            rb.evidenced = True

        # Contradiction: a direct CONTRADICTS edge, or linkage to a Contradiction
        # artefact node.
        if rt == "CONTRADICTS":
            if ra is not None:
                ra.contradicted = True
            if rb is not None:
                rb.contradicted = True
        if a in contradiction_ids and rb is not None:
            rb.contradicted = True
        if b in contradiction_ids and ra is not None:
            ra.contradicted = True


def _mark_duplicates(recs: Iterable[_NodeRec]) -> None:
    """Flag entity nodes sharing a (label, normalized-name) with a sibling."""
    groups: dict[tuple[str, str], list[_NodeRec]] = {}
    for rec in recs:
        if not rec.is_entity:
            continue
        key = (rec.label, _norm_name(rec.name))
        if not key[1]:
            continue
        groups.setdefault(key, []).append(rec)
    for members in groups.values():
        if len(members) > 1:
            for rec in members:
                rec.duplicate = True


def _score_dict(metrics: Mapping[str, float]) -> dict[str, object]:
    hs = kg_health_score(metrics, thresholds=DEFAULT_THRESHOLDS)
    d = hs.as_dict()
    for comp in d["components"]:  # type: ignore[index]
        name = comp["name"]  # type: ignore[index]
        comp["label"] = COMPONENT_LABELS.get(name, name)  # type: ignore[index]
        comp["lower_is_better"] = name in {  # type: ignore[index]
            "orphan_rate",
            "duplicate_rate",
            "contradiction_rate",
            "stale_rate",
        }
    return d


def compute_kg_health(
    store,  # type: ignore[no-untyped-def]
    *,
    dimension: str = "domain",
    stale_years: int = 12,
    current_year: int = 2026,
    worst_k: int = 5,
    min_score: float = 60.0,
) -> dict[str, object]:
    """Compute the composite KG Health Score + per-slice breakdown (§23.24).

    ``dimension`` picks the slice axis (``domain`` / ``material`` / ``property``
    / ``source_type``). ``stale_years`` sets the freshness cutoff; a dated source
    is stale when ``year < current_year - stale_years``. ``min_score`` is the
    demo/CI gate threshold the overall score must clear.

    Returns a JSON-ready dict: overall score/grade/components, raw metrics, a
    census of counts, and the slice breakdown (with the worst areas named).
    """
    if dimension not in _DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}; use one of {sorted(_DIMENSIONS)}")

    stale_cutoff = current_year - max(0, stale_years)

    recs = _load_nodes(store)
    _apply_edges(store, recs)
    _mark_duplicates(recs.values())

    overall = _Bucket()
    slices: dict[str, _Bucket] = {}
    for rec in recs.values():
        overall.add(rec, stale_year_cutoff=stale_cutoff)
        key = rec.slice_key(dimension)
        if key:
            slices.setdefault(key, _Bucket()).add(rec, stale_year_cutoff=stale_cutoff)

    overall_metrics = overall.metrics()
    overall_score = _score_dict(overall_metrics)

    slice_metric_map = {name: b.metrics() for name, b in slices.items() if b.metrics()}
    breakdown_payload: dict[str, object]
    if slice_metric_map:
        report = breakdown(
            slice_metric_map,
            thresholds=DEFAULT_THRESHOLDS,
            worst_k=worst_k,
        )
        enriched = []
        for s in report.slices:
            b = slices[s.slice]
            enriched.append(
                {
                    **s.as_dict(),
                    "size": b.size,
                    "metrics": {k: round(v, 4) for k, v in b.metrics().items()},
                }
            )
        # Sort worst-first so the dashboard leads with the sickest areas.
        enriched.sort(key=lambda e: (e["score"], e["slice"]))  # type: ignore[index,arg-type]
        breakdown_payload = {
            "n": report.n,
            "mean_score": round(report.mean_score, 4),
            "worst": list(report.worst),
            "all_gates_passed": report.all_gates_passed,
            "slices": enriched,
        }
    else:
        breakdown_payload = {
            "n": 0,
            "mean_score": 0.0,
            "worst": [],
            "all_gates_passed": True,
            "slices": [],
        }

    score_val = float(overall_score["score"])  # type: ignore[arg-type]
    return {
        "score": overall_score["score"],
        "grade": overall_score["grade"],
        "gate_passed": overall_score["gate_passed"],
        "failing": overall_score["failing"],
        "components": overall_score["components"],
        "metrics_raw": {k: round(v, 6) for k, v in overall_metrics.items()},
        "dimension": dimension,
        "breakdown": breakdown_payload,
        "census": {
            "nodes": overall.size,
            "claims": overall.claims,
            "entities": overall.entities,
            "dated_sources": overall.dated_sources,
            "orphans": overall.orphans,
            "duplicates": overall.duplicates,
            "evidenced": overall.evidenced,
            "contradicted": overall.contradicted,
            "stale": overall.stale,
            "by_label": dict(sorted(overall.labels.items(), key=lambda kv: -kv[1])),
        },
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "weights": dict(DEFAULT_WEIGHTS),
        "stale_cutoff_year": stale_cutoff,
        "gate": {
            "min_score": min_score,
            "passed": score_val >= min_score and bool(overall_score["gate_passed"]),
        },
    }
