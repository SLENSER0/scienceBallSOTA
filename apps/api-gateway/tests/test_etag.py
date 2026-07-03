"""Tests for ETag computation and conditional caching (§14.17).

Hermetic and dependency-free. Every assertion is a concrete hand-computed
value: a stable sha256 ETag for a known body, a distinct ETag when the body
changes, the 304 match / mismatch of :func:`not_modified` (including ``*``,
weak ``W/`` prefixes and comma lists), the exact :func:`cache_headers` shape,
the empty-body edge case and determinism across repeated calls.
"""

from __future__ import annotations

import hashlib

import pytest
from api_gateway.etag import CacheHeaders, cache_headers, compute_etag, not_modified


def test_compute_etag_stable_known_value() -> None:
    # Hand-computed strong validator for the exact bytes b"hello".
    expected = f'"{hashlib.sha256(b"hello").hexdigest()}"'
    assert compute_etag("hello") == expected
    assert compute_etag(b"hello") == expected


def test_compute_etag_is_quoted_64_hex() -> None:
    tag = compute_etag("payload")
    assert tag.startswith('"') and tag.endswith('"')
    assert len(tag) == 66  # 64 hex chars + 2 quotes
    assert all(c in "0123456789abcdef" for c in tag.strip('"'))


def test_compute_etag_changed_body_new_etag() -> None:
    assert compute_etag("body-v1") != compute_etag("body-v2")


def test_compute_etag_str_and_bytes_agree() -> None:
    assert compute_etag("café") == compute_etag("café".encode())


def test_compute_etag_empty_body() -> None:
    expected = f'"{hashlib.sha256(b"").hexdigest()}"'
    assert compute_etag("") == expected
    assert compute_etag(b"") == expected


def test_compute_etag_deterministic_repeated_calls() -> None:
    tag = compute_etag("determinism")
    assert compute_etag("determinism") == tag == compute_etag("determinism")


def test_not_modified_exact_match_returns_true() -> None:
    tag = compute_etag("cached")
    assert not_modified(tag, tag) is True


def test_not_modified_mismatch_returns_false() -> None:
    assert not_modified(compute_etag("old"), compute_etag("new")) is False


def test_not_modified_none_request_returns_false() -> None:
    assert not_modified(None, compute_etag("x")) is False


def test_not_modified_empty_request_returns_false() -> None:
    assert not_modified("", compute_etag("x")) is False


def test_not_modified_wildcard_matches_any() -> None:
    assert not_modified("*", compute_etag("anything")) is True


def test_not_modified_weak_prefix_matches() -> None:
    tag = compute_etag("weak")
    assert not_modified(f"W/{tag}", tag) is True


def test_not_modified_comma_list_matches_second() -> None:
    tag = compute_etag("target")
    header = f'"{"0" * 64}", {tag}'
    assert not_modified(header, tag) is True


def test_not_modified_comma_list_no_match() -> None:
    header = f'"{"0" * 64}", "{"1" * 64}"'
    assert not_modified(header, compute_etag("missing")) is False


def test_cache_headers_shape_and_values() -> None:
    tag = compute_etag("doc")
    headers = cache_headers(tag, 300)
    assert set(headers.keys()) == {"ETag", "Cache-Control"}
    assert headers["ETag"] == tag
    assert headers["Cache-Control"] == "public, max-age=300"


def test_cache_headers_zero_max_age() -> None:
    headers = cache_headers(compute_etag("z"), 0)
    assert headers["Cache-Control"] == "public, max-age=0"


def test_cache_headers_rejects_negative_max_age() -> None:
    with pytest.raises(ValueError):
        cache_headers(compute_etag("z"), -1)


def test_cache_headers_dataclass_as_dict() -> None:
    hdr = CacheHeaders(etag='"abc"', cache_control="public, max-age=60")
    assert hdr.as_dict() == {"ETag": '"abc"', "Cache-Control": "public, max-age=60"}
