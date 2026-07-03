"""Tests for single-use stream-token auth (§19.2 auth)."""

from __future__ import annotations

import pytest

from kg_common.security.stream_token import StreamToken, mint, parse, verify

_SECRET = "s3cr3t-key"
_SESSION = "sess-1"
_USER = "user-1"
_JTI = "jti-abc"


def _mint(*, issued_at: float = 100.0, ttl_sec: float = 30.0) -> str:
    return mint(_SECRET, _SESSION, _USER, _JTI, issued_at, ttl_sec)


def test_minted_token_verifies_and_matches() -> None:
    token = _mint()
    seen: set[str] = set()
    parsed = verify(_SECRET, token, session_id=_SESSION, user_id=_USER, now=110.0, seen=seen)
    assert parsed.session_id == _SESSION
    assert parsed.user_id == _USER
    assert parsed.jti == _JTI


def test_verify_rejects_expired() -> None:
    token = _mint(issued_at=100.0, ttl_sec=30.0)
    seen: set[str] = set()
    # Exactly at the expiry boundary (130.0) is already invalid.
    with pytest.raises(ValueError, match="expired"):
        verify(_SECRET, token, session_id=_SESSION, user_id=_USER, now=130.0, seen=seen)


def test_verify_rejects_wrong_secret() -> None:
    token = _mint()
    seen: set[str] = set()
    with pytest.raises(ValueError, match="signature mismatch"):
        verify(
            "wrong-secret",
            token,
            session_id=_SESSION,
            user_id=_USER,
            now=110.0,
            seen=seen,
        )


def test_verify_rejects_mismatched_session() -> None:
    token = _mint()
    seen: set[str] = set()
    with pytest.raises(ValueError, match="session_id mismatch"):
        verify(_SECRET, token, session_id="other", user_id=_USER, now=110.0, seen=seen)


def test_verify_rejects_mismatched_user() -> None:
    token = _mint()
    seen: set[str] = set()
    with pytest.raises(ValueError, match="user_id mismatch"):
        verify(_SECRET, token, session_id=_SESSION, user_id="other", now=110.0, seen=seen)


def test_verify_rejects_replay_when_jti_seen() -> None:
    token = _mint()
    seen: set[str] = {_JTI}
    with pytest.raises(ValueError, match="replay"):
        verify(_SECRET, token, session_id=_SESSION, user_id=_USER, now=110.0, seen=seen)


def test_successful_verify_consumes_jti() -> None:
    token = _mint()
    seen: set[str] = set()
    verify(_SECRET, token, session_id=_SESSION, user_id=_USER, now=110.0, seen=seen)
    assert _JTI in seen
    # A second verify against the now-populated set is a replay.
    with pytest.raises(ValueError, match="replay"):
        verify(_SECRET, token, session_id=_SESSION, user_id=_USER, now=110.0, seen=seen)


def test_verify_rejects_tampered_signature() -> None:
    token = _mint()
    payload, sig = token.rsplit(".", 1)
    # Flip the first hex nibble of the signature to a different value.
    flipped = ("0" if sig[0] != "0" else "1") + sig[1:]
    tampered = f"{payload}.{flipped}"
    seen: set[str] = set()
    with pytest.raises(ValueError, match="signature mismatch"):
        verify(_SECRET, tampered, session_id=_SESSION, user_id=_USER, now=110.0, seen=seen)


def test_as_dict_roundtrips_all_fields() -> None:
    tok = StreamToken(
        session_id=_SESSION,
        user_id=_USER,
        jti=_JTI,
        issued_at=100.0,
        expires_at=130.0,
    )
    data = tok.as_dict()
    assert data == {
        "session_id": _SESSION,
        "user_id": _USER,
        "jti": _JTI,
        "issued_at": 100.0,
        "expires_at": 130.0,
    }


def test_parse_rejects_malformed_segment_count() -> None:
    with pytest.raises(ValueError, match="segments"):
        parse("only.three.segments")


def test_parse_rejects_bad_expiry() -> None:
    with pytest.raises(ValueError, match="bad expiry"):
        parse("sess.user.jti.notanumber.deadbeef")
