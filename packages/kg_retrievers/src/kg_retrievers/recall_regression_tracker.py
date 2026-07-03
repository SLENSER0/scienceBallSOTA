"""Cross-snapshot recall regression tracker (§25.17).

Pure-python comparison of two *recall telemetry snapshots* — mappings of a
``context_key`` (e.g. a modality / domain / query-class bucket) to a recall
prior in ``[0, 1]`` — captured *before* and *after* some pipeline change such as
a parser or extractor version bump. :func:`track_regression` joins the two
snapshots on their shared keys and flags every context whose recall dropped by
at least ``epsilon`` (``delta <= -epsilon``).

Трекер регрессий полноты между снимками: сравнивает приоры полноты по контекстам
до и после изменения и помечает контексты с падением полноты.

This is deliberately distinct from :mod:`coverage_delta` (which diffs raw
coverage *cells*) and :mod:`absence_map_delta` (which diffs *verdict* cells):
here the unit of comparison is a per-context recall *prior* (a float), and the
question asked is "did recall regress for this context?".

Keys present in only one of the two snapshots are skipped — a regression is only
meaningful where a before/after pair exists. Results are frozen dataclasses
exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass

# Snapshot type: context key -> recall prior in [0, 1] (приор полноты).
RecallSnapshot = dict[str, float]


@dataclass(frozen=True)
class RecallChange:
    """Per-context recall change between two snapshots (§25.17).

    - ``context_key`` — the shared bucket key;
    - ``before`` / ``after`` — recall priors in the two snapshots;
    - ``delta`` — ``after - before`` (signed; negative means recall dropped);
    - ``regressed`` — ``True`` when ``delta <= -epsilon`` (a real drop).
    """

    context_key: str
    before: float
    after: float
    delta: float
    regressed: bool

    def as_dict(self) -> dict:
        return {
            "context_key": self.context_key,
            "before": self.before,
            "after": self.after,
            "delta": self.delta,
            "regressed": self.regressed,
        }


@dataclass(frozen=True)
class RegressionReport:
    """Aggregate recall-regression report over shared contexts (§25.17).

    - ``changes`` — per-context :class:`RecallChange` rows, sorted by ``delta``
      ascending (most negative / worst first) then by ``context_key``;
    - ``n_regressed`` — number of contexts flagged ``regressed``;
    - ``worst_context`` — key of the most-negative ``delta`` (``None`` if empty);
    - ``mean_delta`` — mean ``delta`` across all shared contexts (``0.0`` if
      empty), rounded to six decimals.
    """

    changes: list[RecallChange]
    n_regressed: int
    worst_context: str | None
    mean_delta: float

    def as_dict(self) -> dict:
        return {
            "changes": [c.as_dict() for c in self.changes],
            "n_regressed": self.n_regressed,
            "worst_context": self.worst_context,
            "mean_delta": self.mean_delta,
        }


def track_regression(
    before: RecallSnapshot,
    after: RecallSnapshot,
    epsilon: float = 0.05,
) -> RegressionReport:
    """Flag contexts whose recall regressed between two snapshots (§25.17).

    Joins ``before`` and ``after`` on shared keys; for each shared context
    computes ``delta = after - before`` and marks ``regressed`` when
    ``delta <= -epsilon``. ``worst_context`` is the key with the most-negative
    ``delta`` (ties broken by key order); ``mean_delta`` averages the deltas of
    the shared contexts. Keys present in only one snapshot are ignored.
    """
    shared = sorted(before.keys() & after.keys())

    changes: list[RecallChange] = []
    for key in shared:
        delta = after[key] - before[key]
        changes.append(
            RecallChange(
                context_key=key,
                before=before[key],
                after=after[key],
                delta=delta,
                regressed=delta <= -epsilon,
            )
        )

    changes.sort(key=lambda c: (c.delta, c.context_key))

    n_regressed = sum(1 for c in changes if c.regressed)
    worst_context = changes[0].context_key if changes else None
    mean_delta = round(sum(c.delta for c in changes) / len(changes), 6) if changes else 0.0

    return RegressionReport(
        changes=changes,
        n_regressed=n_regressed,
        worst_context=worst_context,
        mean_delta=mean_delta,
    )
