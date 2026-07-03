"""CSRF double-submit token tests (§19.7 transport hardening).

All timing is driven by explicit ``now`` arguments — deterministic, no real
``time.sleep``. Values are hand-checkable against the frozen spec assertions.
"""

from __future__ import annotations

from kg_common.security.csrf import CsrfConfig, issue_token, verify_token


def _flip_last(token: str) -> str:
    """Return *token* with its final hex char changed («порча подписи»)."""
    return token[:-1] + ("0" if token[-1] != "0" else "1")


def test_issue_verify_roundtrip_within_default_ttl() -> None:
    cfg = CsrfConfig(b"k")
    t = issue_token(cfg, "s1", 0.0)
    assert verify_token(cfg, "s1", t, 10.0) is True


def test_wrong_session_rejected() -> None:
    cfg = CsrfConfig(b"k")
    t = issue_token(cfg, "s1", 0.0)
    assert verify_token(cfg, "s2", t, 10.0) is False


def test_tampered_signature_rejected() -> None:
    cfg = CsrfConfig(b"k")
    t = issue_token(cfg, "s1", 0.0)
    assert verify_token(cfg, "s1", _flip_last(t), 10.0) is False


def test_ttl_expired_rejected() -> None:
    cfg = CsrfConfig(b"k")
    t = issue_token(cfg, "s1", 0.0)
    assert verify_token(cfg, "s1", t, 3601.0) is False


def test_within_ttl_accepted() -> None:
    cfg = CsrfConfig(b"k")
    t = issue_token(cfg, "s1", 0.0)
    assert verify_token(cfg, "s1", t, 3599.0) is True


def test_exactly_at_ttl_boundary_accepted() -> None:
    cfg = CsrfConfig(b"k")
    t = issue_token(cfg, "s1", 0.0)
    # age == ttl_sec is inclusive.
    assert verify_token(cfg, "s1", t, 3600.0) is True


def test_negative_age_future_token_rejected() -> None:
    cfg = CsrfConfig(b"k")
    # Token issued at t=100 but verified at t=10 -> negative age.
    t = issue_token(cfg, "s1", 100.0)
    assert verify_token(cfg, "s1", t, 10.0) is False


def test_issue_is_deterministic() -> None:
    cfg = CsrfConfig(b"k")
    assert issue_token(cfg, "s1", 0.0) == issue_token(cfg, "s1", 0.0)


def test_custom_ttl_respected() -> None:
    cfg = CsrfConfig(b"k", ttl_sec=5.0)
    t = issue_token(cfg, "s1", 0.0)
    assert verify_token(cfg, "s1", t, 5.0) is True
    assert verify_token(cfg, "s1", t, 5.001) is False


def test_different_secret_yields_different_signature() -> None:
    t1 = issue_token(CsrfConfig(b"k1"), "s1", 0.0)
    t2 = issue_token(CsrfConfig(b"k2"), "s1", 0.0)
    assert t1 != t2
    assert verify_token(CsrfConfig(b"k2"), "s1", t1, 10.0) is False


def test_token_wire_format() -> None:
    cfg = CsrfConfig(b"k")
    t = issue_token(cfg, "s1", 42.9)
    issued, _, sig = t.partition(".")
    # Second timestamp is floored to an int; signature is 64-char hex SHA256.
    assert issued == "42"
    assert len(sig) == 64
    assert all(c in "0123456789abcdef" for c in sig)


def test_malformed_tokens_rejected_without_raising() -> None:
    cfg = CsrfConfig(b"k")
    for bad in ["", ".", "abc", "12.", ".deadbeef", "notint.deadbeef", "12"]:
        assert verify_token(cfg, "s1", bad, 10.0) is False


def test_as_dict_masks_secret() -> None:
    d = CsrfConfig(b"k").as_dict()
    assert d["secret"] != "k"
    assert d["secret"] != b"k"
    assert "k" not in str(d["secret"])  # raw secret never present
    assert d["ttl_sec"] == 3600.0


def test_as_dict_fingerprint_is_stable_and_distinct() -> None:
    assert CsrfConfig(b"k").as_dict()["secret"] == CsrfConfig(b"k").as_dict()["secret"]
    assert CsrfConfig(b"k").as_dict()["secret"] != CsrfConfig(b"other").as_dict()["secret"]
