"""Tests for opaque cursor pagination (§14.12).

Hermetic and dependency-free. Every assertion is a concrete hand-computed
value: round-trip of offset + extras, rejection of malformed tokens, the
last-page / advance-by-limit behaviour of :func:`next_cursor`, both truth
values of ``has_more``, the opacity of the token (the raw offset must not leak
as plain text), the exact :func:`paginate_meta` shape and the offset-0 first
page.
"""

from __future__ import annotations

import base64
import json

import pytest
from api_gateway.cursor import (
    InvalidCursor,
    decode_cursor,
    encode_cursor,
    next_cursor,
    paginate_meta,
)


def test_encode_decode_round_trip_preserves_offset_and_extra() -> None:
    token = encode_cursor(42, extra={"type": "experiment", "dir": "asc"})
    assert decode_cursor(token) == {"o": 42, "type": "experiment", "dir": "asc"}


def test_encode_decode_round_trip_no_extra() -> None:
    assert decode_cursor(encode_cursor(7)) == {"o": 7}


def test_offset_wins_over_extra_key_o() -> None:
    # A stray "o" in extra must not shadow the authoritative offset.
    assert decode_cursor(encode_cursor(9, extra={"o": 999}))["o"] == 9


def test_decode_malformed_raises_invalid_cursor() -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor("not a real cursor!!!")


def test_decode_empty_string_raises_invalid_cursor() -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor("")


def test_decode_valid_base64_but_not_object_raises() -> None:
    # base64 of the JSON scalar "42" — decodes, but is not a payload dict.
    token = base64.urlsafe_b64encode(json.dumps(42).encode("utf-8")).decode("ascii")
    with pytest.raises(InvalidCursor):
        decode_cursor(token)


def test_decode_object_without_offset_key_raises() -> None:
    token = base64.urlsafe_b64encode(json.dumps({"x": 1}).encode("utf-8")).decode("ascii")
    with pytest.raises(InvalidCursor):
        decode_cursor(token)


def test_next_cursor_none_at_last_page() -> None:
    # offset 5 + limit 5 == total 10 → no further page.
    assert next_cursor(offset=5, limit=5, total=10) is None


def test_next_cursor_none_when_offset_beyond_total() -> None:
    assert next_cursor(offset=100, limit=10, total=5) is None


def test_next_cursor_advances_by_limit() -> None:
    token = next_cursor(offset=0, limit=5, total=10)
    assert token is not None
    assert decode_cursor(token)["o"] == 5


def test_next_cursor_second_page_advances_again() -> None:
    token = next_cursor(offset=20, limit=10, total=100)
    assert token is not None
    assert decode_cursor(token)["o"] == 30


def test_has_more_true_when_more_pages_remain() -> None:
    assert paginate_meta(offset=0, limit=5, total=10)["has_more"] is True


def test_has_more_false_on_final_page() -> None:
    meta = paginate_meta(offset=5, limit=5, total=10)
    assert meta["has_more"] is False
    assert meta["next_cursor"] is None


def test_cursor_is_opaque_not_human_readable() -> None:
    token = encode_cursor(12345)
    # The raw offset must not appear verbatim in the opaque token.
    assert "12345" not in token
    # Token stays within the urlsafe-base64 alphabet (no padding leaks either).
    assert all(c.isalnum() or c in "-_" for c in token)
    # …yet it still round-trips back to the original offset.
    assert decode_cursor(token)["o"] == 12345


def test_paginate_meta_shape_and_values() -> None:
    meta = paginate_meta(offset=10, limit=5, total=42)
    assert set(meta.keys()) == {"offset", "limit", "total", "next_cursor", "has_more"}
    assert meta["offset"] == 10
    assert meta["limit"] == 5
    assert meta["total"] == 42
    assert meta["has_more"] is True
    assert meta["next_cursor"] is not None
    assert decode_cursor(meta["next_cursor"])["o"] == 15


def test_paginate_meta_offset_zero_first_page() -> None:
    meta = paginate_meta(offset=0, limit=25, total=200)
    assert meta["offset"] == 0
    assert meta["has_more"] is True
    assert decode_cursor(meta["next_cursor"])["o"] == 25


def test_paginate_meta_single_page_has_no_next() -> None:
    meta = paginate_meta(offset=0, limit=50, total=3)
    assert meta["has_more"] is False
    assert meta["next_cursor"] is None


def test_encode_rejects_negative_offset() -> None:
    with pytest.raises(ValueError):
        encode_cursor(-1)


def test_next_cursor_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        next_cursor(offset=0, limit=0, total=10)
