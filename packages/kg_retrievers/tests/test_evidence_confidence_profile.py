"""§8.3 — hand-checked tests for the evidence confidence & review-status profile.

Builds a tiny temp Kuzu store of :Evidence nodes and checks every aggregate by
hand:

    e_hi  confidence 0.9  review_status accepted
    e_mid confidence 0.4  review_status pending
    e_lo  confidence 0.2  review_status pending

mean = (0.9 + 0.4 + 0.2) / 3 = 0.5; min = 0.2; low (<0.5) = {e_mid, e_lo}.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.evidence_confidence_profile import (
    ConfidenceProfile,
    profile_evidence_confidence,
)
from kg_retrievers.graph_store import KuzuGraphStore

E_HI = make_id("Evidence", "high confidence accepted")
E_MID = make_id("Evidence", "mid confidence pending")
E_LO = make_id("Evidence", "low confidence pending")
E_NONE = make_id("Evidence", "no confidence pending")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _build_three(s: KuzuGraphStore) -> None:
    """Three Evidence nodes with confidences 0.9 / 0.4 / 0.2 and review statuses."""
    s.upsert_node(E_HI, "Evidence", confidence=0.9, review_status="accepted")
    s.upsert_node(E_MID, "Evidence", confidence=0.4, review_status="pending")
    s.upsert_node(E_LO, "Evidence", confidence=0.2, review_status="pending")


def test_three_evidence_mean_min_and_low_ids(store: KuzuGraphStore) -> None:
    _build_three(store)
    prof = profile_evidence_confidence(store)
    assert isinstance(prof, ConfidenceProfile)
    assert prof.n_evidence == 3
    # (0.9 + 0.4 + 0.2) / 3 = 0.5
    assert prof.mean_confidence == pytest.approx(0.5)
    assert prof.min_confidence == pytest.approx(0.2)
    # low (< 0.5) = the 0.4 and 0.2 nodes, exactly.
    assert set(prof.low_confidence_ids) == {E_MID, E_LO}
    assert prof.low_confidence_fraction == pytest.approx(2 / 3)


def test_review_status_counts(store: KuzuGraphStore) -> None:
    _build_three(store)
    prof = profile_evidence_confidence(store)
    assert prof.review_status_counts == {"pending": 2, "accepted": 1}


def test_node_without_confidence_excluded_from_mean_but_counted(store: KuzuGraphStore) -> None:
    _build_three(store)
    # A fourth Evidence node with no numeric confidence at all.
    store.upsert_node(E_NONE, "Evidence", review_status="pending")
    prof = profile_evidence_confidence(store)
    # Counted in n_evidence ...
    assert prof.n_evidence == 4
    # ... but the mean is still over the three scored nodes only: 1.5 / 3 = 0.5.
    assert prof.mean_confidence == pytest.approx(0.5)
    assert prof.min_confidence == pytest.approx(0.2)
    # It is not low-confidence (no numeric confidence to compare).
    assert set(prof.low_confidence_ids) == {E_MID, E_LO}
    # low fraction now over 4: 2 / 4 = 0.5.
    assert prof.low_confidence_fraction == pytest.approx(0.5)
    assert prof.review_status_counts == {"pending": 3, "accepted": 1}


def test_lower_threshold_leaves_only_the_smallest(store: KuzuGraphStore) -> None:
    _build_three(store)
    prof = profile_evidence_confidence(store, low_threshold=0.3)
    # Only the 0.2 node is < 0.3; the 0.4 node is no longer low.
    assert set(prof.low_confidence_ids) == {E_LO}
    assert prof.low_confidence_fraction == pytest.approx(1 / 3)


def test_empty_store_gives_zeroes(store: KuzuGraphStore) -> None:
    prof = profile_evidence_confidence(store)
    assert prof.n_evidence == 0
    assert prof.mean_confidence == 0.0
    assert prof.min_confidence == 0.0
    assert prof.low_confidence_ids == ()
    assert prof.low_confidence_fraction == 0.0
    assert prof.review_status_counts == {}


def test_as_dict_review_status_counts_is_plain_dict(store: KuzuGraphStore) -> None:
    _build_three(store)
    prof = profile_evidence_confidence(store)
    d = prof.as_dict()
    counts = d["review_status_counts"]
    assert type(counts) is dict
    assert counts == {"pending": 2, "accepted": 1}
    # Mutating the copy must not touch the frozen profile's own mapping.
    counts["pending"] = 99
    assert prof.review_status_counts == {"pending": 2, "accepted": 1}
    # Full serialisation is JSON-plain.
    assert d["n_evidence"] == 3
    assert d["low_confidence_ids"] == list(prof.low_confidence_ids)
    assert d["low_confidence_fraction"] == pytest.approx(2 / 3)
