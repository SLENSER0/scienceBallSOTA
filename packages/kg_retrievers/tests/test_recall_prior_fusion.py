"""Tests for recall-prior precedence fusion (§25.17).

Hand-checkable: precedence ordering, calibrated-flag propagation, conflict
thresholding around ``conflict_delta``, conflict counting, single-source keys,
and unknown-method loss.
"""

from __future__ import annotations

from kg_retrievers.recall_prior_fusion import (
    FusedPriors,
    ResolvedPrior,
    _rank,
    fuse_priors,
)


def _prior(context_key: str, recall: float, method: str, calibrated: bool) -> dict:
    """Build a raw prior entry dict (тестовый помощник)."""
    return {
        "context_key": context_key,
        "recall": recall,
        "method": method,
        "calibrated": calibrated,
    }


def test_rank_precedence_order() -> None:
    # gold_calibrated > modality_derived > heuristic > unknown at equal calib.
    assert _rank("gold_calibrated", False) > _rank("heuristic_modality_prior_derived", False)
    assert _rank("heuristic_modality_prior_derived", False) > _rank("heuristic", False)
    assert _rank("heuristic", False) > _rank("unknown", False)
    # Calibrated outranks non-calibrated regardless of method.
    assert _rank("unknown", True) > _rank("gold_calibrated", False)


def test_calibrated_prior_wins_over_heuristic() -> None:
    # Assertion (1): a calibrated prior recall wins over a heuristic prior.
    sources = [
        [_prior("modA", 0.90, "gold_calibrated", True)],
        [_prior("modA", 0.55, "heuristic", False)],
    ]
    fused = fuse_priors(sources)
    resolved = fused.priors["modA"]
    assert resolved.recall == 0.90
    assert resolved.source == "gold_calibrated"


def test_winner_calibrated_flag_propagates() -> None:
    # Assertion (2): winner's calibrated flag propagates to ResolvedPrior.
    sources = [
        [_prior("modA", 0.90, "gold_calibrated", True)],
        [_prior("modA", 0.55, "heuristic", False)],
    ]
    fused = fuse_priors(sources)
    assert fused.priors["modA"].calibrated is True


def test_conflict_true_when_delta_exceeded() -> None:
    # Assertion (3): recalls 0.5 and 0.8 (delta 0.3) -> conflict True.
    sources = [
        [_prior("modA", 0.5, "heuristic", False)],
        [_prior("modA", 0.8, "gold_calibrated", True)],
    ]
    fused = fuse_priors(sources, conflict_delta=0.2)
    assert fused.priors["modA"].conflict is True
    assert fused.n_conflicts == 1


def test_conflict_false_when_within_delta() -> None:
    # Assertion (4): recalls 0.5 and 0.6 (delta 0.1) -> conflict False.
    sources = [
        [_prior("modA", 0.5, "heuristic", False)],
        [_prior("modA", 0.6, "gold_calibrated", True)],
    ]
    fused = fuse_priors(sources, conflict_delta=0.2)
    assert fused.priors["modA"].conflict is False
    assert fused.n_conflicts == 0


def test_n_conflicts_counts_flagged_keys() -> None:
    # Assertion (5): n_conflicts counts only the keys flagged as conflicts.
    sources = [
        [
            _prior("modA", 0.5, "heuristic", False),
            _prior("modB", 0.5, "heuristic", False),
            _prior("modC", 0.5, "heuristic", False),
        ],
        [
            _prior("modA", 0.9, "gold_calibrated", True),  # delta 0.4 -> conflict
            _prior("modB", 0.55, "gold_calibrated", True),  # delta 0.05 -> ok
            _prior("modC", 0.85, "gold_calibrated", True),  # delta 0.35 -> conflict
        ],
    ]
    fused = fuse_priors(sources, conflict_delta=0.2)
    assert fused.priors["modA"].conflict is True
    assert fused.priors["modB"].conflict is False
    assert fused.priors["modC"].conflict is True
    assert fused.n_conflicts == 2


def test_single_source_key_no_conflict() -> None:
    # Assertion (6): a key present in only one source -> conflict False.
    sources = [
        [_prior("solo", 0.42, "heuristic", False)],
        [_prior("other", 0.7, "gold_calibrated", True)],
    ]
    fused = fuse_priors(sources)
    assert fused.priors["solo"].conflict is False
    assert fused.n_conflicts == 0


def test_unknown_method_loses_to_known() -> None:
    # Assertion (7): an 'unknown' method entry loses to any known-method entry.
    sources = [
        [_prior("modA", 0.30, "unknown", False)],
        [_prior("modA", 0.44, "heuristic", False)],
    ]
    fused = fuse_priors(sources, conflict_delta=0.2)
    resolved = fused.priors["modA"]
    assert resolved.source == "heuristic"
    assert resolved.recall == 0.44
    # delta 0.14 <= 0.2 -> no conflict.
    assert resolved.conflict is False


def test_as_dict_round_trip() -> None:
    fused = fuse_priors([[_prior("modA", 0.7, "gold_calibrated", True)]])
    d = fused.as_dict()
    assert d["n_conflicts"] == 0
    assert d["priors"]["modA"] == {
        "context_key": "modA",
        "recall": 0.7,
        "source": "gold_calibrated",
        "calibrated": True,
        "conflict": False,
    }
    # Frozen dataclass instances are returned in the object view.
    assert isinstance(fused, FusedPriors)
    assert isinstance(fused.priors["modA"], ResolvedPrior)
