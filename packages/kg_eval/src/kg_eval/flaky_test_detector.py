"""Flaky-test detection from repeated run outcomes (§23).

To gate the eval/CI suite we replay a test's outcomes across many runs and flag the
ones that are **non-deterministic** — sometimes passing, sometimes failing on the same
code (нестабильные тесты). Such tests poison a green/red gate: a flaky failure blocks a
good change, a flaky pass hides a real regression, so we quarantine them.

Input is a flat sequence of run records, each a mapping with a ``test_id`` and an
``outcome`` of ``"pass"`` or ``"fail"``. Records are grouped by ``test_id`` **in order
of appearance**, and within a test the outcomes keep their given order so consecutive
runs can be compared.

For each test we report:

* ``runs`` — total records for the test,
* ``passes`` / ``fails`` — outcome counts (``passes + fails == runs`` always; any
  outcome other than ``"pass"`` counts as a fail),
* ``flip_rate`` — transitions between consecutive differing outcomes divided by
  ``runs - 1`` (доля переключений), ``0.0`` when a test has a single run,
* ``is_flaky`` — ``True`` iff the test has at least one pass **and** one fail across at
  least ``min_runs`` runs.

The :class:`FlakyReport` collects every test plus a sorted ``quarantine`` tuple of the
flaky ``test_id``s — the list a CI gate excludes or reruns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class FlakyTest:
    """One test's aggregated outcomes and flakiness verdict (§23).

    ``runs`` is the record count, ``passes``/``fails`` the outcome tallies (always
    summing to ``runs``), ``flip_rate`` the fraction of consecutive-run transitions, and
    ``is_flaky`` the gate verdict. ``as_dict`` rounds ``flip_rate`` to 4 decimals.
    """

    test_id: str
    runs: int
    passes: int
    fails: int
    flip_rate: float
    is_flaky: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "test_id": self.test_id,
            "runs": self.runs,
            "passes": self.passes,
            "fails": self.fails,
            "flip_rate": round(self.flip_rate, 4),
            "is_flaky": self.is_flaky,
        }


@dataclass(frozen=True)
class FlakyReport:
    """All analysed tests plus the sorted quarantine list (§23).

    ``tests`` keeps first-seen order; ``quarantine`` is the sorted tuple of flaky
    ``test_id``s. ``as_dict`` nests each test via its own ``as_dict`` as a list.
    """

    tests: tuple[FlakyTest, ...]
    quarantine: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "tests": [test.as_dict() for test in self.tests],
            "quarantine": list(self.quarantine),
        }


def _flip_rate(outcomes: Sequence[bool]) -> float:
    """Consecutive-differing transitions over ``len - 1``; ``0.0`` for a single run."""
    if len(outcomes) < 2:
        return 0.0
    transitions = sum(1 for a, b in pairwise(outcomes) if a != b)
    return transitions / (len(outcomes) - 1)


def analyze(runs: Sequence[Mapping[str, object]], *, min_runs: int = 3) -> FlakyReport:
    """Aggregate run records into per-test flakiness verdicts (§23).

    Records are grouped by ``test_id`` in order of appearance; per-test outcomes keep
    their given order. A test is flaky iff it has at least one pass and one fail across
    at least ``min_runs`` runs. ``quarantine`` is the sorted tuple of flaky ``test_id``s.
    """
    ordered_ids: list[str] = []
    outcomes_by_id: dict[str, list[bool]] = {}
    for record in runs:
        test_id = str(record["test_id"])
        passed = record["outcome"] == "pass"
        if test_id not in outcomes_by_id:
            outcomes_by_id[test_id] = []
            ordered_ids.append(test_id)
        outcomes_by_id[test_id].append(passed)

    tests: list[FlakyTest] = []
    for test_id in ordered_ids:
        outcomes = outcomes_by_id[test_id]
        run_count = len(outcomes)
        passes = sum(outcomes)
        fails = run_count - passes
        is_flaky = passes >= 1 and fails >= 1 and run_count >= min_runs
        tests.append(
            FlakyTest(
                test_id=test_id,
                runs=run_count,
                passes=passes,
                fails=fails,
                flip_rate=_flip_rate(outcomes),
                is_flaky=is_flaky,
            )
        )

    quarantine = tuple(sorted(test.test_id for test in tests if test.is_flaky))
    return FlakyReport(tests=tuple(tests), quarantine=quarantine)
