"""Tests for endpoint tier + limit-key policy (§19.4)."""

from __future__ import annotations

from kg_common.security.ratelimit_policy import (
    LimitTier,
    endpoint_tier,
    rate_limit_key,
    tier_for,
)


def test_auth_login_is_auth_tier() -> None:
    assert endpoint_tier("POST", "/api/v1/auth/login") == "auth"


def test_chat_messages_post_is_heavy() -> None:
    assert endpoint_tier("POST", "/api/v1/chat/sessions/1/messages") == "heavy"


def test_document_read_is_light() -> None:
    assert endpoint_tier("GET", "/api/v1/documents/5") == "light"


def test_search_hybrid_post_is_heavy() -> None:
    assert endpoint_tier("POST", "/api/v1/search/hybrid") == "heavy"


def test_auth_tier_keys_by_ip() -> None:
    assert rate_limit_key("auth", "u1", "1.2.3.4") == "ip:1.2.3.4"


def test_heavy_tier_keys_by_user() -> None:
    assert rate_limit_key("heavy", "u1", "x") == "user:u1"


def test_anonymous_light_keys_by_ip() -> None:
    assert rate_limit_key("light", None, "9.9.9.9") == "ip:9.9.9.9"


def test_limit_tier_as_dict_rpm() -> None:
    assert LimitTier("heavy", 30, 10).as_dict()["rpm"] == 30


# --- extra hand-checkable coverage --------------------------------------------


def test_heavy_suffixes_all_classified() -> None:
    for suffix in ("search/hybrid", "graph/query", "gaps/scan", "documents/upload", "ingest/jobs"):
        assert endpoint_tier("POST", f"/api/v1/{suffix}") == "heavy"


def test_heavy_suffix_requires_post() -> None:
    # GET on a heavy path stays light — only the expensive write/search is heavy.
    assert endpoint_tier("GET", "/api/v1/search/hybrid") == "light"


def test_auth_wins_over_method() -> None:
    assert endpoint_tier("GET", "/api/v1/auth/refresh") == "auth"


def test_trailing_slash_normalized() -> None:
    assert endpoint_tier("POST", "/api/v1/gaps/scan/") == "heavy"


def test_tier_for_resolves_and_missing_raises() -> None:
    tiers = {
        "heavy": LimitTier("heavy", 30, 10),
        "light": LimitTier("light", 120, 40),
    }
    assert tier_for("heavy", tiers).rpm == 30
    assert tier_for("light", tiers) is tiers["light"]
    try:
        tier_for("auth", tiers)
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError for missing tier")
