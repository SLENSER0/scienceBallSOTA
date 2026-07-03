"""Extractor-recall priors from coverage telemetry (§25.10).

All expected recall values are hand-derivable from the Beta-smoothing formula
``(n_found + a) / (n_attempts + a + b)`` with the default ``prior_strength=20``
and neutral mean ``m = 0.7`` → ``a = 14``, ``b = 6``.
"""

from __future__ import annotations

import pytest

from kg_common.storage.base import CoverageEvent
from kg_common.storage.sql import SqlMetaStore
from kg_retrievers.recall_priors import (
    DERIVED_EXTRACTOR,
    NEUTRAL_RECALL,
    derive_prior_details,
    derive_recall_priors,
    persist_recall_priors,
    smoothed_recall,
    to_extractor_recall,
)


@pytest.fixture
def store() -> SqlMetaStore:
    s = SqlMetaStore("sqlite:///:memory:")
    s.migrate()
    return s


def _seed(
    store: SqlMetaStore,
    target_type: str,
    n_attempts: int,
    n_found: int,
    *,
    extractor: str = "rule",
    doc: str = "d1",
    attempted: bool = True,
) -> None:
    """Log ``n_attempts`` distinct-key coverage events, the first ``n_found`` of which hit."""
    for i in range(n_attempts):
        store.log_coverage(
            CoverageEvent(
                doc_id=doc,
                chunk_id=f"{target_type}-{i}",
                extractor=extractor,
                target_type=target_type,
                attempted=attempted,
                found_count=1 if i < n_found else 0,
            )
        )


def _by_type(priors: list) -> dict:
    return {p.target_type: p for p in priors}


def test_more_found_yields_higher_recall(store: SqlMetaStore) -> None:
    # Measurement hits 8/10, TechnologySolution 2/10 → the well-covered type must
    # earn the higher smoothed recall (§25.10).
    _seed(store, "Measurement", 10, 8)
    _seed(store, "TechnologySolution", 10, 2)
    priors = _by_type(derive_recall_priors(store))

    assert priors["Measurement"].recall == pytest.approx(22 / 30)  # (8+14)/(10+20)
    assert priors["TechnologySolution"].recall == pytest.approx(16 / 30)  # (2+14)/30
    assert priors["Measurement"].recall > priors["TechnologySolution"].recall


def test_zero_attempts_falls_back_to_neutral_default(store: SqlMetaStore) -> None:
    # A logged-but-not-attempted cell has n_attempts == 0, so the estimate has no
    # evidence and must collapse to the neutral prior mean (§25.10).
    _seed(store, "Absent", 3, 0, attempted=False)
    priors = _by_type(derive_recall_priors(store))

    assert priors["Absent"].sample_size == 0  # no attempts backed this prior
    assert priors["Absent"].recall == pytest.approx(NEUTRAL_RECALL)  # 14/20 = 0.7
    assert smoothed_recall(0, 0) == pytest.approx(NEUTRAL_RECALL)


def test_smoothing_keeps_values_in_open_unit_interval(store: SqlMetaStore) -> None:
    # Even the degenerate all-hit / no-hit cells are pulled strictly inside (0, 1).
    _seed(store, "AllHit", 5, 5)
    _seed(store, "NoHit", 5, 0)
    priors = _by_type(derive_recall_priors(store))

    assert priors["AllHit"].recall == pytest.approx(19 / 25)  # (5+14)/(5+20) = 0.76
    assert priors["NoHit"].recall == pytest.approx(14 / 25)  # (0+14)/25 = 0.56
    for p in priors.values():
        assert 0.0 < p.recall < 1.0


def test_persist_round_trips_via_get_recall_priors(store: SqlMetaStore) -> None:
    _seed(store, "Measurement", 10, 8)
    _seed(store, "TechnologySolution", 10, 2)
    written = _by_type(persist_recall_priors(store))

    reread = _by_type(store.get_recall_priors())
    assert set(reread) == {"Measurement", "TechnologySolution"}
    for tt, prior in written.items():
        assert reread[tt].recall == pytest.approx(prior.recall)
        assert reread[tt].extractor == DERIVED_EXTRACTOR
        assert reread[tt].sample_size == 10  # n_attempts carried through
    assert reread["Measurement"].recall == pytest.approx(22 / 30)


def test_to_extractor_recall_for_property(store: SqlMetaStore) -> None:
    # Persisted priors flow into ExtractorRecall.per_entity_type so the absence
    # layer can resolve a data-driven recall per entity type (§25.10 / §25.11).
    _seed(store, "Measurement", 10, 8)
    persist_recall_priors(store)
    recall = to_extractor_recall(store)

    seen = recall.for_property("recovery", "Measurement")
    assert seen == pytest.approx(22 / 30)  # entity-type prior wins
    assert 0.0 < seen < 1.0
    # an entity type we never observed falls back to the neutral default
    assert recall.for_property("recovery", "TechnologySolution") == pytest.approx(NEUTRAL_RECALL)
    assert recall.for_property("recovery") == pytest.approx(NEUTRAL_RECALL)


def test_prior_strength_controls_shrinkage(store: SqlMetaStore) -> None:
    # hit-rate 0.9 vs neutral 0.7: a weaker prior trusts the data more, so its
    # estimate sits closer to 0.9 than the strong prior's does (§25.10).
    _seed(store, "Measurement", 10, 9)
    strong = _by_type(derive_recall_priors(store, prior_strength=20.0))
    weak = _by_type(derive_recall_priors(store, prior_strength=2.0))

    assert strong["Measurement"].recall == pytest.approx(23 / 30)  # (9+14)/30 ≈ 0.767
    assert weak["Measurement"].recall == pytest.approx(10.4 / 12)  # (9+1.4)/(10+2) ≈ 0.867
    assert weak["Measurement"].recall > strong["Measurement"].recall
    assert 0.7 < strong["Measurement"].recall < weak["Measurement"].recall < 0.9


def test_derive_prior_details_provenance_and_as_dict(store: SqlMetaStore) -> None:
    _seed(store, "Measurement", 10, 8)
    details = derive_prior_details(store)
    assert len(details) == 1
    d = details[0]

    assert d.n_attempts == 10 and d.n_found == 8
    assert d.hit_rate == pytest.approx(0.8)  # raw n_found / n_attempts
    assert d.recall == pytest.approx(22 / 30)  # smoothed, != raw hit_rate
    assert d.recall != pytest.approx(d.hit_rate)
    dumped = d.as_dict()
    assert dumped["target_type"] == "Measurement"
    assert dumped["recall"] == pytest.approx(22 / 30)
    assert dumped["prior_strength"] == pytest.approx(20.0)


def test_persist_is_idempotent(store: SqlMetaStore) -> None:
    _seed(store, "Measurement", 10, 8)
    _seed(store, "TechnologySolution", 10, 2)
    persist_recall_priors(store)
    persist_recall_priors(store)  # re-deriving must UPSERT, not duplicate rows

    reread = store.get_recall_priors()
    assert len(reread) == 2  # one prior per target_type, no dups
    assert _by_type(reread)["Measurement"].recall == pytest.approx(22 / 30)
