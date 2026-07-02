"""MetaStore tests (§25.4): idempotent coverage, recall priors, backend parity."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from kg_common.storage import (
    CoverageEvent,
    MetaStore,
    RecallPrior,
    SqlMetaStore,
)

SEED_COVERAGE = [
    CoverageEvent("d1", "c1", "rule", "Measurement", found_count=2, run_id="r1"),
    CoverageEvent("d1", "c2", "rule", "Measurement", found_count=0, run_id="r1"),
    CoverageEvent("d1", "c1", "llm", "Measurement", found_count=1, run_id="r1"),
    CoverageEvent("d2", "c9", "rule", "Measurement", found_count=3, run_id="r1"),
    CoverageEvent("d2", "c9", "rule", "TechnologySolution", found_count=0, run_id="r1"),
]


@pytest.fixture
def store() -> SqlMetaStore:
    s = SqlMetaStore("sqlite:///:memory:")
    s.migrate()
    return s


def _load(s: SqlMetaStore, events: list[CoverageEvent]) -> None:
    for e in events:
        s.log_coverage(e)


def test_protocol_conformance(store: SqlMetaStore) -> None:
    assert isinstance(store, MetaStore)  # runtime_checkable Protocol


def test_migrate_idempotent(store: SqlMetaStore) -> None:
    store.migrate()
    store.migrate()  # second call must not raise


def test_coverage_upsert_no_duplicates(store: SqlMetaStore) -> None:
    _load(store, SEED_COVERAGE)
    # re-log the same key with a new count — must UPDATE, not insert a dup
    store.log_coverage(CoverageEvent("d1", "c2", "rule", "Measurement", found_count=5, run_id="r2"))
    stats = {s.target_type: s for s in store.coverage_stats()}
    meas = stats["Measurement"]
    # 4 distinct (doc,chunk,extractor,target) Measurement keys — not 5
    assert meas.n_chunks == 4
    assert meas.n_attempts == 4
    # d1/c2 now found_count=5>0, plus d1/c1(rule,2), d1/c1(llm,1), d2/c9(rule,3) = 4 found
    assert meas.n_found == 4
    assert meas.n_docs == 2


def test_coverage_stats_filters(store: SqlMetaStore) -> None:
    _load(store, SEED_COVERAGE)
    only_d1 = store.coverage_stats(doc_id="d1")
    assert all(s.n_docs == 1 for s in only_d1)
    tech = store.coverage_stats(target_type="TechnologySolution")
    assert len(tech) == 1 and tech[0].n_found == 0
    assert tech[0].hit_rate == 0.0


def test_hit_rate(store: SqlMetaStore) -> None:
    _load(store, SEED_COVERAGE)
    meas = store.coverage_stats(target_type="Measurement")[0]
    assert 0.0 < meas.hit_rate <= 1.0
    assert meas.hit_rate == pytest.approx(meas.n_found / meas.n_attempts)


def test_recall_prior_upsert(store: SqlMetaStore) -> None:
    store.save_recall_prior(RecallPrior("rule", "Measurement", 0.6, 50))
    store.save_recall_prior(RecallPrior("rule", "Measurement", 0.72, 120))  # update
    store.save_recall_prior(RecallPrior("llm", "Measurement", 0.8, 40))
    priors = store.get_recall_priors(target_type="Measurement")
    assert len(priors) == 2  # rule updated in place, not duplicated
    rule = next(p for p in priors if p.extractor == "rule")
    assert rule.recall == pytest.approx(0.72) and rule.sample_size == 120


def test_file_backed_persistence() -> None:
    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{Path(d) / 'meta.db'}"
        s1 = SqlMetaStore(url)
        s1.migrate()
        _load(s1, SEED_COVERAGE)
        # reopen — data survives
        s2 = SqlMetaStore(url)
        assert s2.coverage_stats(target_type="Measurement")[0].n_chunks == 4


def _parity_second_url() -> str:
    """Real Postgres if provided (CI/server profile), else a 2nd SQLite engine."""
    return os.environ.get("METASTORE_PARITY_URL", "sqlite:///:memory:")


def test_backend_parity() -> None:
    """SQLite and the parity backend return identical stats/priors on one seed.

    In CI ``METASTORE_PARITY_URL`` points at a real Postgres (server profile);
    locally it falls back to a second independent SQLite engine, proving the
    shared code path is deterministic and backend-independent.
    """
    a = SqlMetaStore("sqlite:///:memory:")
    b = SqlMetaStore(_parity_second_url())
    for s in (a, b):
        s.migrate()
        _load(s, SEED_COVERAGE)
        s.save_recall_prior(RecallPrior("rule", "Measurement", 0.72, 120))

    assert a.coverage_stats() == b.coverage_stats()
    assert a.get_recall_priors() == b.get_recall_priors()
