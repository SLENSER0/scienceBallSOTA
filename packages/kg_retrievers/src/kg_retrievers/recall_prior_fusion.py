"""Recall-prior precedence fusion (§25.17).

Слияние приоритетов recall — different subsystems each estimate the *recall*
prior for a retrieval context (a ``context_key`` such as a modality or query
class): a gold calibrated measurement, a modality-derived heuristic, a plain
heuristic, or an unknown-method fallback. When several sources speak about the
same key they may disagree; this module fuses them by a fixed precedence order
and keeps the single highest-precedence estimate per key.

Precedence (highest first):

1. ``gold_calibrated``            — a calibrated gold measurement.
2. ``heuristic_modality_prior_derived`` — heuristic derived from a modality prior.
3. ``heuristic``                  — a plain heuristic estimate.
4. ``unknown``                    — anything else / unlabelled.

A calibrated entry (``calibrated=True``) always outranks a non-calibrated one,
regardless of method. Beyond picking a winner, the fuser flags a *conflict* on a
key when any two contributing sources disagree in recall by more than
``conflict_delta`` — a signal that the priors are inconsistent and worth review.

The module is pure/in-memory: it takes plain prior dicts and returns frozen
dataclasses. It performs no graph or I/O access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Method label of a calibrated gold measurement (highest precedence).
METHOD_GOLD_CALIBRATED = "gold_calibrated"

# Method label of a heuristic derived from a modality prior.
METHOD_MODALITY_DERIVED = "heuristic_modality_prior_derived"

# Method label of a plain heuristic estimate.
METHOD_HEURISTIC = "heuristic"

# Method label / fallback for an unlabelled or unrecognised source.
METHOD_UNKNOWN = "unknown"

# Precedence rank per method — higher wins. Calibrated adds a rank bump so a
# calibrated entry always outranks a non-calibrated one of the same method.
_METHOD_RANK: dict[str, int] = {
    METHOD_GOLD_CALIBRATED: 3,
    METHOD_MODALITY_DERIVED: 2,
    METHOD_HEURISTIC: 1,
    METHOD_UNKNOWN: 0,
}

# Rank offset applied when an entry is calibrated (лучше некалиброванного).
_CALIBRATED_BUMP = 10


def _rank(method: str, calibrated: bool) -> int:
    """Precedence rank for a (method, calibrated) pair — higher wins.

    Ранг приоритета: gold_calibrated > heuristic_modality_prior_derived >
    heuristic > unknown, with any calibrated entry outranking a non-calibrated
    one via a fixed bump so calibration dominates method ordering.
    """
    base = _METHOD_RANK.get(method, _METHOD_RANK[METHOD_UNKNOWN])
    return base + (_CALIBRATED_BUMP if calibrated else 0)


@dataclass(frozen=True)
class ResolvedPrior:
    """The winning recall prior chosen for one ``context_key`` (§25.17)."""

    context_key: str
    recall: float
    source: str
    calibrated: bool
    conflict: bool

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view (сериализация) of this resolved prior."""
        return {
            "context_key": self.context_key,
            "recall": self.recall,
            "source": self.source,
            "calibrated": self.calibrated,
            "conflict": self.conflict,
        }


@dataclass(frozen=True)
class FusedPriors:
    """Fusion result: winning prior per key plus the conflict count (§25.17)."""

    priors: dict[str, ResolvedPrior]
    n_conflicts: int

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view (сериализация) of the fused priors."""
        return {
            "priors": {key: p.as_dict() for key, p in self.priors.items()},
            "n_conflicts": self.n_conflicts,
        }


def _entry_recall(entry: dict) -> float:
    """Recall value of a raw prior entry as ``float`` (без изменения знака)."""
    return float(entry["recall"])


def fuse_priors(
    sources: list[list[dict]],
    *,
    conflict_delta: float = 0.2,
) -> FusedPriors:
    """Fuse recall priors from multiple sources by precedence (§25.17).

    Каждый источник — список dict ``{context_key, recall, method, calibrated}``.
    Entries are grouped by ``context_key``; the highest-precedence entry (per
    :func:`_rank`) wins each key. A key is flagged ``conflict=True`` when any two
    contributing entries differ in recall by more than ``conflict_delta``.

    :param sources: list of prior lists, one per contributing subsystem.
    :param conflict_delta: recall spread above which a key is a conflict.
    :returns: a :class:`FusedPriors` with the winning prior per key and the
        number of keys flagged as conflicts.
    """
    # Gather every entry per context_key, preserving arrival order.
    grouped: dict[str, list[dict]] = {}
    for source in sources:
        for entry in source:
            grouped.setdefault(entry["context_key"], []).append(entry)

    priors: dict[str, ResolvedPrior] = {}
    n_conflicts = 0

    for context_key, entries in grouped.items():
        # Winner = highest rank; ties resolve to the first-seen entry.
        winner = max(
            entries,
            key=lambda e: _rank(
                e.get("method", METHOD_UNKNOWN),
                bool(e.get("calibrated", False)),
            ),
        )

        recalls = [_entry_recall(e) for e in entries]
        conflict = (max(recalls) - min(recalls)) > conflict_delta
        if conflict:
            n_conflicts += 1

        priors[context_key] = ResolvedPrior(
            context_key=context_key,
            recall=_entry_recall(winner),
            source=winner.get("method", METHOD_UNKNOWN),
            calibrated=bool(winner.get("calibrated", False)),
            conflict=conflict,
        )

    return FusedPriors(priors=priors, n_conflicts=n_conflicts)
