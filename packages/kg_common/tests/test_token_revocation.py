"""Tests for the access-token ``jti`` revocation blacklist (§19.2)."""

from __future__ import annotations

from kg_common.security.token_revocation import RevocationList, RevokedToken


def test_revoked_token_still_active_before_expiry() -> None:
    """(1) After revoke(j, 100), is_revoked(j, 50) is True."""
    rl = RevocationList()
    rl.revoke("j", 100.0)
    assert rl.is_revoked("j", 50.0) is True


def test_revoked_token_past_expiry_not_revoked() -> None:
    """(2) is_revoked(j, 150) is False once now is past expiry."""
    rl = RevocationList()
    rl.revoke("j", 100.0)
    assert rl.is_revoked("j", 150.0) is False


def test_prune_removes_expired_entry() -> None:
    """(3) prune(150) returns 1 and removes the expired token."""
    rl = RevocationList()
    rl.revoke("j", 100.0)
    assert rl.prune(150.0) == 1
    assert len(rl) == 0


def test_prune_keeps_active_entry() -> None:
    """(4) prune(50) returns 0 and keeps the still-active token."""
    rl = RevocationList()
    rl.revoke("j", 100.0)
    assert rl.prune(50.0) == 0
    assert len(rl) == 1


def test_revoking_same_jti_twice_keeps_one_entry() -> None:
    """(5) Revoking the same jti twice keeps len == 1."""
    rl = RevocationList()
    rl.revoke("j", 100.0)
    rl.revoke("j", 200.0)
    assert len(rl) == 1
    # Overwrite took effect: still revoked at now=150 under the new expiry.
    assert rl.is_revoked("j", 150.0) is True


def test_is_revoked_unknown_jti_is_false() -> None:
    """(6) is_revoked on an unknown jti is False."""
    rl = RevocationList()
    assert rl.is_revoked("never-seen", 0.0) is False


def test_active_contains_revoked_token() -> None:
    """(7) active(50) contains the RevokedToken for the live entry."""
    rl = RevocationList()
    rl.revoke("j", 100.0)
    active = rl.active(50.0)
    assert active == (RevokedToken(jti="j", expires_at=100.0),)


def test_active_excludes_expired() -> None:
    """active(150) omits an entry already past its expiry."""
    rl = RevocationList()
    rl.revoke("j", 100.0)
    assert rl.active(150.0) == ()


def test_revoked_token_as_dict_has_fields() -> None:
    """(8) RevokedToken.as_dict has jti and expires_at."""
    d = RevokedToken(jti="abc", expires_at=42.0).as_dict()
    assert d == {"jti": "abc", "expires_at": 42.0}
