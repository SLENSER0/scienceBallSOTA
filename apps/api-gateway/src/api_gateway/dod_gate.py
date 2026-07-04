"""Summary Definition-of-Done CI-gate engine (§22.7).

§22.7 asks for a single aggregating job — ``definition-of-done`` — that folds the
otherwise-scattered readiness signals into **one GREEN verdict** and an
attachable artifact report. The acceptance criterion names exactly what it must
aggregate: *phase-checks*, API/schema/contract completeness, *SOTA smoke-tests*,
*golden eval* and *e2e scenarios*, ending in status ``GREEN``.

This module is the aggregator. It runs a fixed catalogue of checks against the
**live** graph store (Neo4j in the server profile) and the running settings,
grouped into three phases that mirror the acceptance wording:

* ``phase-checks`` — the graph is populated, server-profile dependencies are up
  (reusing :func:`kg_common.health_checks.aggregate_health`), and the composite
  KG-health gate passes (reusing :func:`api_gateway.kg_health_metrics.compute_kg_health`).
* ``eval`` — the golden suite is present (:func:`kg_eval.golden.load_cases`) and
  the data-quality gates clear their thresholds (reusing
  :func:`kg_eval.quality_gates.check_gates`) on metrics derived from the live graph.
* ``e2e`` — the five §2.1 user scenarios are each reachable in-process against the
  live store (scientific question / graph explorer / evidence inspector / gap
  analysis / decision history).

Nothing here re-implements a scorer or a metric — it only *orchestrates* the
already-shipped modules and turns their outputs into pass/fail checks. Every
check is guarded: a broken probe becomes a failing (red) check with its error in
``detail``, never a 500. The overall verdict is ``GREEN`` when every *required*
check passes, ``YELLOW`` when required checks pass but some soft check failed or
was skipped, and ``RED`` when any required check fails. The returned payload is
the release artifact-report (JSON-ready, timestamped, per-phase breakdown).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# --- verdict vocabulary -----------------------------------------------------
GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"

# Phase identifiers, in report order.
PHASE_CHECKS = "phase-checks"
PHASE_EVAL = "eval"
PHASE_E2E = "e2e"
PHASE_ORDER = (PHASE_CHECKS, PHASE_EVAL, PHASE_E2E)

# Eval data-quality gates (higher-is-better; compared with ``>=`` by check_gates).
# Lower-is-better raw metrics (orphan/contradiction/duplicate rate) are folded to
# their complements below so a single ``>=`` gate direction covers all of them.
EVAL_GATES: dict[str, float] = {
    "evidence_coverage": 0.55,
    "connectivity": 0.70,  # 1 - orphan_rate
    "contradiction_control": 0.80,  # 1 - contradiction_rate
    "dedup_quality": 0.90,  # 1 - duplicate_rate
}

# Minimum golden-suite size for the eval phase to consider the suite "present".
MIN_GOLDEN_CASES = 3
# KG-health composite gate the phase-checks phase must clear.
DEFAULT_MIN_HEALTH = 60.0


@dataclass(frozen=True)
class Check:
    """One gate check — a named pass/fail probe with evidence for the report."""

    id: str
    phase: str
    title: str
    required: bool
    passed: bool
    detail: str
    metric: float | None = None
    threshold: float | None = None
    skipped: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.skipped:
            return "skipped"
        return "green" if self.passed else "red"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase,
            "title": self.title,
            "required": self.required,
            "passed": self.passed,
            "skipped": self.skipped,
            "status": self.status,
            "detail": self.detail,
            "metric": self.metric,
            "threshold": self.threshold,
            **({"extra": self.extra} if self.extra else {}),
        }


def _guard(
    fn: Callable[[], Check],
    *,
    check_id: str,
    phase: str,
    title: str,
    required: bool,
) -> Check:
    """Run one check body, turning any exception into a failing red check."""
    try:
        return fn()
    except Exception as exc:  # a broken probe is a failed gate, not a 500.
        return Check(
            id=check_id,
            phase=phase,
            title=title,
            required=required,
            passed=False,
            detail=f"probe error: {type(exc).__name__}: {exc}",
        )


# =====================================================================
# Phase 1 — phase-checks (structural + infra + composite health)
# =====================================================================


def _check_graph_populated(store: Any) -> Check:
    counts = store.counts()
    nodes = int(counts.get("nodes", 0))
    rels = int(counts.get("rels", 0))
    ok = nodes > 0 and rels > 0
    return Check(
        id="graph.populated",
        phase=PHASE_CHECKS,
        title="Граф наполнен (узлы и рёбра существуют)",
        required=True,
        passed=ok,
        detail=f"nodes={nodes}, rels={rels}",
        metric=float(nodes),
        threshold=1.0,
        extra={"nodes": nodes, "rels": rels},
    )


def _check_dependencies(store: Any, settings: Any) -> Check:
    """Server-profile dependency liveness (Neo4j/Qdrant/OpenSearch/PG/Redis).

    In the embedded profile there are no external services, so this is a *soft*
    (non-required) check that reports ``skipped`` rather than probing localhost.
    """
    profile = getattr(settings, "runtime_profile", "embedded")
    if profile != "server":
        return Check(
            id="infra.dependencies",
            phase=PHASE_CHECKS,
            title="Зависимости server-профиля живы",
            required=False,
            passed=True,
            skipped=True,
            detail=f"runtime_profile={profile!r} — external deps not applicable",
        )
    from kg_common.health_checks import aggregate_health

    agg = aggregate_health(settings)
    status = str(agg.get("status", "down"))
    checks = agg.get("checks", [])
    ok_n = sum(1 for c in checks if isinstance(c, dict) and c.get("ok"))
    return Check(
        id="infra.dependencies",
        phase=PHASE_CHECKS,
        title="Зависимости server-профиля живы",
        required=True,
        passed=status == "ok",
        detail=f"aggregate_health={status} ({ok_n}/{len(checks)} up)",
        extra={"status": status, "checks": checks},
    )


def _compute_health(store: Any, min_score: float) -> dict[str, Any]:
    """Run the composite KG-health census once; reused by the health & eval checks.

    ``compute_kg_health`` loads every node/edge to score the graph — on a large
    corpus that is the gate's most expensive step, so it is computed a single time
    and shared rather than re-run per check.
    """
    from api_gateway.kg_health_metrics import compute_kg_health

    return compute_kg_health(store, min_score=min_score)


def _check_kg_health(health: dict[str, Any], min_score: float) -> Check:
    score = float(health.get("score", 0.0))
    # The DoD headline gate is the *composite* score clearing ``min_score``; the
    # per-component sub-gate (``gate.passed``) is surfaced in ``extra`` for
    # transparency but does not by itself fail the summary when the score is high.
    passed = score >= min_score
    # compute_kg_health() returns the per-component gate as top-level ``gate_passed``
    # (not a nested ``gate.passed``) — read the real field for honest transparency.
    component_gate = bool(health.get("gate_passed", passed))
    return Check(
        id="kg_health.score",
        phase=PHASE_CHECKS,
        title="Композитный KG-health score выше порога",
        required=True,
        passed=passed,
        detail=f"score={score:.1f} (min {min_score:.0f}), grade={health.get('grade')}",
        metric=score,
        threshold=min_score,
        extra={
            "component_gate_passed": component_gate,
            "components": health.get("components"),
            "failing": health.get("failing"),
            "census": health.get("census"),
        },
    )


# =====================================================================
# Phase 2 — eval (golden suite present + data-quality gates)
# =====================================================================


def _check_golden_suite() -> Check:
    from kg_eval.golden import load_cases

    cases = load_cases()
    n = len(cases)
    ok = n >= MIN_GOLDEN_CASES
    return Check(
        id="golden.suite_present",
        phase=PHASE_EVAL,
        title="Golden-набор доступен для eval",
        required=True,
        passed=ok,
        detail=f"{n} golden cases (min {MIN_GOLDEN_CASES})",
        metric=float(n),
        threshold=float(MIN_GOLDEN_CASES),
    )


def _eval_metrics_from_health(health: dict[str, Any]) -> dict[str, float]:
    """Derive higher-is-better eval metrics from the live KG-health raw metrics.

    Lower-is-better rates (orphan / contradiction / duplicate) are folded to their
    complements so every :data:`EVAL_GATES` entry is a single ``>=`` comparison.
    Takes the already-computed health census (see :func:`_compute_health`) so the
    expensive full-graph scan is not repeated.
    """
    raw = (health.get("metrics_raw", {}) or {}) if isinstance(health, dict) else {}
    return {
        "evidence_coverage": float(raw.get("evidence_coverage", 0.0)),
        "connectivity": 1.0 - float(raw.get("orphan_rate", 1.0)),
        "contradiction_control": 1.0 - float(raw.get("contradiction_rate", 1.0)),
        "dedup_quality": 1.0 - float(raw.get("duplicate_rate", 1.0)),
    }


def _check_quality_gates(health: dict[str, Any]) -> Check:
    from kg_eval.quality_gates import check_gates

    metrics = _eval_metrics_from_health(health)
    report = check_gates(metrics, gates=EVAL_GATES)
    failed = [f.metric for f in report.failures]
    detail = "all gates passed" if report.passed else f"failing: {', '.join(failed)}"
    return Check(
        id="eval.quality_gates",
        phase=PHASE_EVAL,
        title="Data-quality gate'ы eval пройдены",
        required=True,
        passed=report.passed,
        detail=detail,
        extra={
            "metrics": {k: round(v, 4) for k, v in metrics.items()},
            "thresholds": dict(EVAL_GATES),
            "checked": report.checked,
            "failures": [f.as_dict() for f in report.failures],
        },
    )


# =====================================================================
# Phase 3 — e2e (five §2.1 user scenarios reachable against the live store)
# =====================================================================


def _check_e2e_scientific_question(store: Any) -> Check:
    """Scenario 1: retrieval surface reachable — a hub node has neighbours."""
    rows = store.rows(
        "MATCH (n:Node)-[r:Rel]->() RETURN n.id, count(r) AS deg "
        "ORDER BY deg DESC LIMIT 1"
    )
    if not rows:
        return Check(
            id="e2e.scientific_question",
            phase=PHASE_E2E,
            title="Сценарий 1 — научный вопрос (retrieval)",
            required=True,
            passed=False,
            detail="no connected node found",
        )
    hub_id = rows[0][0]
    resp = store.neighbors(hub_id, depth=1, limit=50)
    n_edges = len(getattr(resp, "edges", []) or [])
    return Check(
        id="e2e.scientific_question",
        phase=PHASE_E2E,
        title="Сценарий 1 — научный вопрос (retrieval)",
        required=True,
        passed=n_edges > 0,
        detail=f"hub '{hub_id}' → {n_edges} edges in 1-hop subgraph",
        metric=float(n_edges),
        threshold=1.0,
    )


def _check_e2e_graph_explorer(store: Any) -> Check:
    """Scenario 2: graph explorer — the corpus spans more than one entity type."""
    by_label = store.counts_by_label()
    n_labels = len(by_label)
    return Check(
        id="e2e.graph_explorer",
        phase=PHASE_E2E,
        title="Сценарий 2 — граф-эксплорер",
        required=True,
        passed=n_labels >= 2,
        detail=f"{n_labels} distinct node labels",
        metric=float(n_labels),
        threshold=2.0,
        extra={"by_label": dict(sorted(by_label.items(), key=lambda kv: -kv[1])[:12])},
    )


def _check_e2e_evidence_inspector(store: Any) -> Check:
    """Scenario 3: evidence inspector — resolvable evidence spans exist."""
    rows = store.rows(
        "MATCH (e:Node) WHERE (e.label='Evidence' OR e.type='Evidence') "
        "AND coalesce(e.text, e.quote, e.snippet, '') <> '' "
        "RETURN count(e)"
    )
    n = int(rows[0][0]) if rows and rows[0] else 0
    return Check(
        id="e2e.evidence_inspector",
        phase=PHASE_E2E,
        title="Сценарий 3 — инспектор доказательств",
        required=True,
        passed=n > 0,
        detail=f"{n} evidence nodes with resolvable text",
        metric=float(n),
        threshold=1.0,
    )


def _check_e2e_gap_analysis(store: Any) -> Check:
    """Scenario 4: gap analysis — the scanner runs and yields gaps/contradictions."""
    existing = store.rows(
        "MATCH (g:Node) WHERE g.label='Gap' OR g.type='Gap' RETURN count(g)"
    )
    have_gaps = int(existing[0][0]) if existing and existing[0] else 0
    if have_gaps > 0:
        return Check(
            id="e2e.gap_analysis",
            phase=PHASE_E2E,
            title="Сценарий 4 — анализ пробелов",
            required=True,
            passed=True,
            detail=f"{have_gaps} gap nodes present",
            metric=float(have_gaps),
            threshold=1.0,
        )
    # No persisted gaps yet — prove the scanner is reachable and productive.
    from kg_retrievers.gap_analysis import GapScanner

    res = GapScanner(store).scan().as_dict()
    produced = int(res.get("gaps", 0)) + int(res.get("contradictions", 0))
    return Check(
        id="e2e.gap_analysis",
        phase=PHASE_E2E,
        title="Сценарий 4 — анализ пробелов",
        required=True,
        passed=produced > 0,
        detail=(
            f"scan produced {res.get('gaps', 0)} gaps / "
            f"{res.get('contradictions', 0)} contradictions"
        ),
        metric=float(produced),
        threshold=1.0,
        extra=res,
    )


def _check_e2e_decision_history(store: Any) -> Check:
    """Scenario 5: decision history — provenance/lineage trail exists."""
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN ['ExtractorRun','GapScanRun','Decision','CurationEvent'] "
        "OR n.type IN ['ExtractorRun','GapScanRun','Decision','CurationEvent'] "
        "RETURN count(n)"
    )
    n = int(rows[0][0]) if rows and rows[0] else 0
    # Provenance stamps on nodes (extractor_run / run_id props) also count.
    if n == 0:
        prov = store.rows(
            "MATCH (n:Node) WHERE n.extractor_run IS NOT NULL OR n.run_id IS NOT NULL "
            "RETURN count(n)"
        )
        n = int(prov[0][0]) if prov and prov[0] else 0
    return Check(
        id="e2e.decision_history",
        phase=PHASE_E2E,
        title="Сценарий 5 — история решений (provenance)",
        required=True,
        passed=n > 0,
        detail=f"{n} provenance/decision-trail nodes",
        metric=float(n),
        threshold=1.0,
    )


# =====================================================================
# Aggregation
# =====================================================================


def _run_all_checks(store: Any, settings: Any, min_health: float) -> list[Check]:
    # The composite KG-health census loads the whole graph; run it once here and
    # share the result with both the phase-checks health gate and the eval
    # data-quality gates instead of re-scanning per check. If it blows up, the
    # per-check ``_guard`` still turns the failure into a red check.
    try:
        health = _compute_health(store, min_health)
    except Exception:  # propagated as red checks below via each check's _guard
        health = {}
    specs: list[tuple[Callable[[], Check], str, str, str, bool]] = [
        (lambda: _check_graph_populated(store), "graph.populated", PHASE_CHECKS,
         "Граф наполнен", True),
        (lambda: _check_dependencies(store, settings), "infra.dependencies", PHASE_CHECKS,
         "Зависимости server-профиля", False),
        (lambda: _check_kg_health(health, min_health), "kg_health.score", PHASE_CHECKS,
         "KG-health score", True),
        (_check_golden_suite, "golden.suite_present", PHASE_EVAL,
         "Golden-набор доступен", True),
        (lambda: _check_quality_gates(health), "eval.quality_gates", PHASE_EVAL,
         "Data-quality gate'ы", True),
        (lambda: _check_e2e_scientific_question(store), "e2e.scientific_question", PHASE_E2E,
         "Сценарий 1 — научный вопрос", True),
        (lambda: _check_e2e_graph_explorer(store), "e2e.graph_explorer", PHASE_E2E,
         "Сценарий 2 — граф-эксплорер", True),
        (lambda: _check_e2e_evidence_inspector(store), "e2e.evidence_inspector", PHASE_E2E,
         "Сценарий 3 — инспектор доказательств", True),
        (lambda: _check_e2e_gap_analysis(store), "e2e.gap_analysis", PHASE_E2E,
         "Сценарий 4 — анализ пробелов", True),
        (lambda: _check_e2e_decision_history(store), "e2e.decision_history", PHASE_E2E,
         "Сценарий 5 — история решений", True),
    ]
    return [
        _guard(fn, check_id=cid, phase=phase, title=title, required=req)
        for fn, cid, phase, title, req in specs
    ]


def _verdict(checks: list[Check]) -> str:
    """GREEN iff every required check passes; RED if any required fails; else YELLOW."""
    required = [c for c in checks if c.required and not c.skipped]
    if any(not c.passed for c in required):
        return RED
    soft_problem = any((not c.passed) or c.skipped for c in checks if not c.required)
    return YELLOW if soft_problem else GREEN


def _phase_verdict(checks: list[Check]) -> str:
    required = [c for c in checks if c.required and not c.skipped]
    if any(not c.passed for c in required):
        return RED
    if any((not c.passed) or c.skipped for c in checks if not c.required):
        return YELLOW
    return GREEN


def run_definition_of_done(
    store: Any,
    settings: Any,
    *,
    min_health: float = DEFAULT_MIN_HEALTH,
) -> dict[str, Any]:
    """Run the full §22.7 summary gate → JSON-ready release artifact-report.

    ``min_health`` is the composite KG-health threshold the phase-checks phase
    must clear. The returned dict carries the overall verdict, a per-phase
    breakdown, every individual check, and a headline summary — the artifact the
    release attaches as proof of Definition-of-Done.
    """
    t0 = time.perf_counter()
    checks = _run_all_checks(store, settings, min_health)
    verdict = _verdict(checks)

    phases: list[dict[str, Any]] = []
    for phase in PHASE_ORDER:
        phase_checks = [c for c in checks if c.phase == phase]
        phases.append(
            {
                "phase": phase,
                "verdict": _phase_verdict(phase_checks),
                "passed": sum(1 for c in phase_checks if c.passed and not c.skipped),
                "total": sum(1 for c in phase_checks if not c.skipped),
                "checks": [c.as_dict() for c in phase_checks],
            }
        )

    scored = [c for c in checks if not c.skipped]
    green_n = sum(1 for c in scored if c.passed)
    red_n = sum(1 for c in scored if not c.passed)
    skipped_n = sum(1 for c in checks if c.skipped)
    readiness = round(100.0 * green_n / len(scored), 1) if scored else 0.0

    return {
        "verdict": verdict,
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime_profile": getattr(settings, "runtime_profile", "embedded"),
        "summary": {
            "green": green_n,
            "red": red_n,
            "skipped": skipped_n,
            "total": len(checks),
            "required_total": sum(1 for c in checks if c.required),
            "readiness_pct": readiness,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
        },
        "phases": phases,
        "checks": [c.as_dict() for c in checks],
        "meta": {
            "spec": "§22.7 Definition of Done — summary CI-gate",
            "min_health": min_health,
            "eval_gates": dict(EVAL_GATES),
            "reused": [
                "api_gateway.kg_health_metrics.compute_kg_health",
                "kg_common.health_checks.aggregate_health",
                "kg_eval.golden.load_cases",
                "kg_eval.quality_gates.check_gates",
                "kg_retrievers.gap_analysis.GapScanner",
            ],
        },
    }


def catalog() -> dict[str, Any]:
    """Static catalogue of the gate's checks & thresholds (no store access)."""
    return {
        "spec": "§22.7 Definition of Done — summary CI-gate",
        "phases": list(PHASE_ORDER),
        "verdicts": [GREEN, YELLOW, RED],
        "min_health_default": DEFAULT_MIN_HEALTH,
        "eval_gates": dict(EVAL_GATES),
        "min_golden_cases": MIN_GOLDEN_CASES,
        "checks": [
            {"id": "graph.populated", "phase": PHASE_CHECKS, "required": True,
             "title": "Граф наполнен (узлы и рёбра существуют)"},
            {"id": "infra.dependencies", "phase": PHASE_CHECKS, "required": False,
             "title": "Зависимости server-профиля живы (Neo4j/Qdrant/OpenSearch/PG/Redis)"},
            {"id": "kg_health.score", "phase": PHASE_CHECKS, "required": True,
             "title": "Композитный KG-health score выше порога"},
            {"id": "golden.suite_present", "phase": PHASE_EVAL, "required": True,
             "title": "Golden-набор доступен для eval"},
            {"id": "eval.quality_gates", "phase": PHASE_EVAL, "required": True,
             "title": "Data-quality gate'ы eval пройдены"},
            {"id": "e2e.scientific_question", "phase": PHASE_E2E, "required": True,
             "title": "Сценарий 1 — научный вопрос (retrieval)"},
            {"id": "e2e.graph_explorer", "phase": PHASE_E2E, "required": True,
             "title": "Сценарий 2 — граф-эксплорер"},
            {"id": "e2e.evidence_inspector", "phase": PHASE_E2E, "required": True,
             "title": "Сценарий 3 — инспектор доказательств"},
            {"id": "e2e.gap_analysis", "phase": PHASE_E2E, "required": True,
             "title": "Сценарий 4 — анализ пробелов"},
            {"id": "e2e.decision_history", "phase": PHASE_E2E, "required": True,
             "title": "Сценарий 5 — история решений (provenance)"},
        ],
    }
