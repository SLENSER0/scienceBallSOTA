"""Per-extraction-run rollup joining coverage telemetry with provenance (§25.5/§25.3).

Where :mod:`kg_retrievers.coverage_report` rolls raw seen/emitted telemetry up **by
modality** (context-keyed) and :mod:`kg_retrievers.observation_lineage` walks the
per-observation provenance edges, this module answers a third, orthogonal question:
*for one extraction run (прогон извлечения), how much did it see, how much did it
emit, and how many of the observations it produced still stand?*

It joins two flat inputs on a shared run key (``extraction_run_id`` by default):

- ``coverage_events`` — seen/emitted telemetry rows (``seen_segments`` /
  ``emitted_facts``), summed per run into the honest denominator ``total_seen``;
- ``observations`` — the observations (наблюдения) that run produced, counted as
  active (активные) vs. retracted (отозванные, ``retracted`` prop truthy).

``yield_ratio`` = emitted / seen is the observed yield, reported as ``0.0`` when a
run saw nothing (never divide-by-zero) — a run that emitted zero from many seen
segments is a real blind spot (слепая зона), never silently dropped. A run that
appears only in ``observations`` gets ``seen_segments == 0`` and ``yield_ratio ==
0.0``. Pure Python and read-only: reads no store and writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass


def _yield_ratio(emitted: int, seen: int) -> float:
    """Наблюдаемый выход emitted / seen; ``0.0`` when ``seen`` is 0 (no divide-by-zero)."""
    return emitted / seen if seen else 0.0


@dataclass(frozen=True)
class RunLedgerRow:
    """Coverage + provenance rollup for one extraction run (§25.5/§25.3).

    Attributes:
        run_id: the extraction-run key (прогон извлечения).
        seen_segments: Σ segments seen by the run (Σ ``seen_segments``).
        emitted_facts: Σ facts emitted by the run (Σ ``emitted_facts``).
        yield_ratio: observed yield = emitted / seen, ``0.0`` when seen is 0.
        n_observations: total observations (наблюдения) attributed to the run.
        n_active: observations still standing (активные) = total − retracted.
        n_retracted: observations retracted (отозванные, ``retracted`` truthy).
    """

    run_id: str
    seen_segments: int
    emitted_facts: int
    yield_ratio: float
    n_observations: int
    n_active: int
    n_retracted: int

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "seen_segments": self.seen_segments,
            "emitted_facts": self.emitted_facts,
            "yield_ratio": self.yield_ratio,
            "n_observations": self.n_observations,
            "n_active": self.n_active,
            "n_retracted": self.n_retracted,
        }


@dataclass(frozen=True)
class RunLedger:
    """All per-run rows plus corpus-wide seen/emitted/retracted totals (§25.5/§25.3)."""

    rows: tuple[RunLedgerRow, ...]
    total_seen: int
    total_emitted: int
    total_retracted: int

    def as_dict(self) -> dict:
        return {
            "rows": [r.as_dict() for r in self.rows],
            "total_seen": self.total_seen,
            "total_emitted": self.total_emitted,
            "total_retracted": self.total_retracted,
        }


def build_run_ledger(
    coverage_events: list[dict],
    observations: list[dict],
    *,
    run_key: str = "extraction_run_id",
) -> RunLedger:
    """Join coverage telemetry with observation provenance per extraction run (§25.5/§25.3).

    Groups both inputs by ``run_key``, sums ``seen_segments`` / ``emitted_facts`` per
    run, and counts each run's observations as active vs. retracted (``retracted``
    prop truthy). Runs present in either input appear; a run seen only among
    ``observations`` gets ``seen_segments == 0`` and ``yield_ratio == 0.0``. Rows are
    sorted by ``run_id``.

    Args:
        coverage_events: seen/emitted telemetry rows keyed by ``run_key``.
        observations: observation rows keyed by ``run_key``; a truthy ``retracted``
            prop marks a retracted (отозванное) observation.
        run_key: dict key carrying the run id on both inputs.

    Returns:
        A :class:`RunLedger` with per-run rows sorted by ``run_id`` and totals.
    """
    seen: dict[str, int] = {}
    emitted: dict[str, int] = {}
    n_obs: dict[str, int] = {}
    n_retracted: dict[str, int] = {}

    for event in coverage_events:
        run_id = str(event.get(run_key, ""))
        seen[run_id] = seen.get(run_id, 0) + int(event.get("seen_segments", 0))
        emitted[run_id] = emitted.get(run_id, 0) + int(event.get("emitted_facts", 0))
        n_obs.setdefault(run_id, 0)
        n_retracted.setdefault(run_id, 0)

    for obs in observations:
        run_id = str(obs.get(run_key, ""))
        seen.setdefault(run_id, 0)
        emitted.setdefault(run_id, 0)
        n_obs[run_id] = n_obs.get(run_id, 0) + 1
        n_retracted.setdefault(run_id, 0)
        if obs.get("retracted"):
            n_retracted[run_id] += 1

    rows: list[RunLedgerRow] = []
    for run_id in sorted(seen):
        run_seen = seen[run_id]
        run_emitted = emitted[run_id]
        total_obs = n_obs.get(run_id, 0)
        retracted = n_retracted.get(run_id, 0)
        rows.append(
            RunLedgerRow(
                run_id=run_id,
                seen_segments=run_seen,
                emitted_facts=run_emitted,
                yield_ratio=_yield_ratio(run_emitted, run_seen),
                n_observations=total_obs,
                n_active=total_obs - retracted,
                n_retracted=retracted,
            )
        )

    return RunLedger(
        rows=tuple(rows),
        total_seen=sum(seen.values()),
        total_emitted=sum(emitted.values()),
        total_retracted=sum(n_retracted.values()),
    )
