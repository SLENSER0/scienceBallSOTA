"""Definition-of-Done summary CI-gate HTTP surface (§22.7).

Thin FastAPI wrapper over :mod:`api_gateway.dod_gate` — the aggregator that folds
phase-checks + eval + e2e into one GREEN/YELLOW/RED verdict and a release
artifact-report. The router contains no gate logic of its own: it resolves the
live store + settings and delegates to :func:`api_gateway.dod_gate.run_definition_of_done`.

* ``GET /api/v1/definition-of-done/info`` — static catalogue of checks/thresholds.
* ``GET /api/v1/definition-of-done/gate`` — run the full gate, return the report;
  the HTTP status mirrors the verdict (200 GREEN/YELLOW, 503 RED) so a CI curl or
  a k8s readiness probe can gate on the response code alone.
* ``GET /api/v1/definition-of-done/artifact`` — same report, always 200, sent as a
  downloadable JSON attachment for the ``v1.0`` release bundle.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from api_gateway import dod_gate
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/definition-of-done", tags=["definition-of-done"])


def _run(min_health: float) -> dict:
    from kg_common import get_settings

    return dod_gate.run_definition_of_done(
        get_store(), get_settings(), min_health=min_health
    )


@router.get("/info")
def info() -> dict:
    """Static catalogue of the gate's checks, phases and thresholds (§22.7)."""
    return dod_gate.catalog()


@router.get("/gate")
def gate(
    response: Response,
    min_health: float = Query(default=dod_gate.DEFAULT_MIN_HEALTH, ge=0.0, le=100.0),
) -> dict:
    """Run the full Definition-of-Done gate; status code mirrors the verdict.

    Returns ``200`` for GREEN/YELLOW and ``503`` for RED so a plain ``curl -f`` in
    CI (or a readiness probe) can gate purely on the HTTP status.
    """
    report = _run(min_health)
    if report["verdict"] == dod_gate.RED:
        response.status_code = 503
    return report


@router.get("/artifact")
def artifact(
    min_health: float = Query(default=dod_gate.DEFAULT_MIN_HEALTH, ge=0.0, le=100.0),
) -> JSONResponse:
    """The gate report as a downloadable JSON artifact for the release bundle."""
    report = _run(min_health)
    return JSONResponse(
        content=report,
        headers={
            "Content-Disposition": 'attachment; filename="definition-of-done.json"'
        },
    )
