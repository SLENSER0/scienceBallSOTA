"""Tests for per-user concurrency quota accounting (§19.4)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.security.concurrency_quota import ConcurrencyQuota, ConcurrencyTracker


def test_quota_as_dict() -> None:
    quota = ConcurrencyQuota(per_user_max=2, global_max=10)
    assert quota.as_dict() == {"per_user_max": 2, "global_max": 10}
    assert quota.as_dict()["global_max"] == 10


def test_quota_is_frozen() -> None:
    quota = ConcurrencyQuota(per_user_max=2, global_max=10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        quota.per_user_max = 5  # type: ignore[misc]


def test_quota_rejects_negative() -> None:
    with pytest.raises(ValueError):
        ConcurrencyQuota(per_user_max=-1, global_max=10)
    with pytest.raises(ValueError):
        ConcurrencyQuota(per_user_max=2, global_max=-1)


def test_per_user_ceiling() -> None:
    tracker = ConcurrencyTracker(ConcurrencyQuota(per_user_max=2, global_max=10))
    assert tracker.try_acquire("a") is True
    assert tracker.try_acquire("a") is True
    assert tracker.in_use("a") == 2
    # Third acquire for the same user is over per_user_max.
    assert tracker.try_acquire("a") is False
    assert tracker.in_use("a") == 2
    assert tracker.global_in_use() == 2


def test_release_frees_a_slot() -> None:
    tracker = ConcurrencyTracker(ConcurrencyQuota(per_user_max=2, global_max=10))
    assert tracker.try_acquire("a") is True
    assert tracker.try_acquire("a") is True
    tracker.release("a")
    assert tracker.in_use("a") == 1
    assert tracker.global_in_use() == 1
    # A freed slot can be re-acquired.
    assert tracker.try_acquire("a") is True
    assert tracker.in_use("a") == 2


def test_global_ceiling_blocks_other_user() -> None:
    tracker = ConcurrencyTracker(ConcurrencyQuota(per_user_max=1, global_max=1))
    assert tracker.try_acquire("a") is True
    # b is under its per-user limit but the global pool is full.
    assert tracker.try_acquire("b") is False
    assert tracker.in_use("b") == 0
    assert tracker.in_use("a") == 1
    assert tracker.global_in_use() == 1


def test_release_unknown_user_no_negative() -> None:
    tracker = ConcurrencyTracker(ConcurrencyQuota(per_user_max=2, global_max=10))
    tracker.release("nobody")
    assert tracker.global_in_use() == 0
    assert tracker.in_use("nobody") == 0


def test_release_never_below_zero_after_acquire() -> None:
    tracker = ConcurrencyTracker(ConcurrencyQuota(per_user_max=2, global_max=10))
    assert tracker.try_acquire("a") is True
    tracker.release("a")
    tracker.release("a")  # extra release is a no-op
    assert tracker.in_use("a") == 0
    assert tracker.global_in_use() == 0


def test_single_acquire_in_use() -> None:
    tracker = ConcurrencyTracker(ConcurrencyQuota(per_user_max=2, global_max=10))
    assert tracker.try_acquire("a") is True
    assert tracker.in_use("a") == 1


def test_two_users_count_toward_global() -> None:
    tracker = ConcurrencyTracker(ConcurrencyQuota(per_user_max=2, global_max=10))
    assert tracker.try_acquire("a") is True
    assert tracker.try_acquire("b") is True
    assert tracker.in_use("a") == 1
    assert tracker.in_use("b") == 1
    assert tracker.global_in_use() == 2


def test_tracker_exposes_quota() -> None:
    quota = ConcurrencyQuota(per_user_max=2, global_max=10)
    tracker = ConcurrencyTracker(quota)
    assert tracker.quota is quota
