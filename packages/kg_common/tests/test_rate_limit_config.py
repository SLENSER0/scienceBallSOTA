"""Per-role rate-limit config tests (§19.13, on top of §19.8 token bucket).

Every asserted value is hand-checked against the bucket capacities declared in
the fixture: ``admin`` gets the largest budget, ``guest`` the smallest, and any
role without an entry falls back to ``default``.
"""

from __future__ import annotations

import pytest

from kg_common.rate_limit_config import RateLimitConfig
from kg_common.ratelimit import TokenBucket


def _config() -> RateLimitConfig:
    return RateLimitConfig(
        default=TokenBucket(capacity=10, refill_per_sec=1.0),
        per_role={
            "admin": TokenBucket(capacity=100, refill_per_sec=10.0),
            "guest": TokenBucket(capacity=2, refill_per_sec=0.5),
        },
    )


def test_bucket_for_known_role_returns_its_bucket() -> None:
    # "guest" is explicitly configured, so its own small bucket is returned.
    cfg = _config()
    assert cfg.bucket_for("guest") == TokenBucket(capacity=2, refill_per_sec=0.5)


def test_bucket_for_unknown_role_falls_back_to_default() -> None:
    # "robot" has no entry, so bucket_for yields the shared default bucket.
    cfg = _config()
    assert cfg.bucket_for("robot") == TokenBucket(capacity=10, refill_per_sec=1.0)


def test_admin_has_higher_limit_than_guest_and_default() -> None:
    # admin capacity 100 > default 10 > guest 2 — the intended role ordering.
    cfg = _config()
    assert cfg.bucket_for("admin").capacity == 100.0
    assert cfg.bucket_for("admin").capacity > cfg.bucket_for("robot").capacity
    assert cfg.bucket_for("robot").capacity > cfg.bucket_for("guest").capacity


def test_as_dict_renders_nested_bucket_dicts() -> None:
    cfg = _config()
    assert cfg.as_dict() == {
        "default": {"capacity": 10.0, "refill_per_sec": 1.0},
        "per_role": {
            "admin": {"capacity": 100.0, "refill_per_sec": 10.0},
            "guest": {"capacity": 2.0, "refill_per_sec": 0.5},
        },
    }


def test_from_dict_round_trips_as_dict() -> None:
    cfg = _config()
    rebuilt = RateLimitConfig.from_dict(cfg.as_dict())
    assert rebuilt.as_dict() == cfg.as_dict()
    assert rebuilt.bucket_for("admin") == TokenBucket(capacity=100, refill_per_sec=10.0)


def test_from_dict_without_per_role_uses_only_default() -> None:
    # A minimal policy: just a default bucket, no per-role overrides.
    cfg = RateLimitConfig.from_dict({"default": {"capacity": 5, "refill_per_sec": 0.0}})
    assert cfg.bucket_for("anyone") == TokenBucket(capacity=5, refill_per_sec=0.0)
    assert cfg.as_dict()["per_role"] == {}


def test_from_dict_validates_bucket_capacity() -> None:
    # capacity <= 0 is rejected by TokenBucket, inherited through from_dict.
    with pytest.raises(ValueError, match="capacity must be > 0"):
        RateLimitConfig.from_dict({"default": {"capacity": 0, "refill_per_sec": 1.0}})


def test_config_per_role_is_immutable() -> None:
    # The frozen config exposes a read-only mapping; mutation must fail.
    cfg = _config()
    with pytest.raises(TypeError):
        cfg.per_role["admin"] = TokenBucket(capacity=1, refill_per_sec=0.0)  # type: ignore[index]
