"""Login brute-force lockout tracker (§19.2 auth)."""

from __future__ import annotations

from kg_common.security.login_guard import LockoutPolicy, LoginAttemptTracker


def test_four_failures_do_not_lock() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    for _ in range(4):
        t.record_failure("u", now=0.0)
    assert t.failure_count("u", now=0.0) == 4
    assert t.is_locked("u", now=0.0) is False


def test_fifth_failure_locks() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    for _ in range(5):
        t.record_failure("u", now=0.0)
    assert t.is_locked("u", now=0.0) is True


def test_lockout_elapses_after_lockout_sec() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    for _ in range(5):
        t.record_failure("u", now=0.0)
    assert t.is_locked("u", now=0.0) is True
    assert t.is_locked("u", now=901.0) is False  # 900s lockout elapsed


def test_retry_after_equals_lockout_sec_right_after_locking() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    for _ in range(5):
        t.record_failure("u", now=0.0)
    assert t.retry_after("u", now=0.0) == 900.0


def test_retry_after_zero_when_not_locked() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    t.record_failure("u", now=0.0)
    assert t.retry_after("u", now=0.0) == 0.0
    assert t.retry_after("unknown", now=0.0) == 0.0


def test_success_clears_state() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    for _ in range(5):
        t.record_failure("u", now=0.0)
    assert t.is_locked("u", now=0.0) is True
    t.record_success("u")
    assert t.is_locked("u", now=0.0) is False
    assert t.failure_count("u", now=0.0) == 0


def test_failures_pruned_by_window() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    for _ in range(3):
        t.record_failure("u", now=0.0)
    # 1000s later, all now=0 failures fall outside the 900s window.
    assert t.failure_count("u", now=1000.0) == 0


def test_unknown_key_is_not_locked() -> None:
    t = LoginAttemptTracker(LockoutPolicy())
    assert t.is_locked("unknown", now=0.0) is False


def test_policy_as_dict() -> None:
    d = LockoutPolicy().as_dict()
    assert d["max_failed"] == 5
    assert d == {"max_failed": 5, "lockout_sec": 900.0, "window_sec": 900.0}


def test_window_prune_does_not_prevent_lock_within_window() -> None:
    # Failures spread inside the window still accumulate to a lock.
    t = LoginAttemptTracker(LockoutPolicy(max_failed=3, window_sec=100.0))
    t.record_failure("u", now=0.0)
    t.record_failure("u", now=50.0)
    assert t.is_locked("u", now=50.0) is False
    t.record_failure("u", now=90.0)
    assert t.is_locked("u", now=90.0) is True


def test_old_failures_pruned_do_not_trip_lock() -> None:
    # An early failure ages out before enough recent ones accumulate.
    t = LoginAttemptTracker(LockoutPolicy(max_failed=3, window_sec=100.0))
    t.record_failure("u", now=0.0)  # will be pruned by now=200
    t.record_failure("u", now=150.0)
    t.record_failure("u", now=200.0)
    assert t.failure_count("u", now=200.0) == 2
    assert t.is_locked("u", now=200.0) is False
