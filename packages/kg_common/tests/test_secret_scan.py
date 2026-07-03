"""Secret detection tests (§19.10)."""

from __future__ import annotations

from itertools import pairwise

from kg_common.secret_scan import SecretHit, redact, scan_secrets

# A hand-built JWT (three base64url segments) — hand-checked, not a live token.
_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)
# ``sk-`` + 48-char tail; a synthetic key, not a real credential.
_SK = "sk-abcdefghij0123456789abcdefghij0123456789ABCDEF"
# Canonical AWS docs example access-key id (AKIA + 16 chars = 20).
_AKIA = "AKIAIOSFODNN7EXAMPLE"


def _kinds(text: str) -> list[str]:
    return [h.kind for h in scan_secrets(text)]


def test_sk_api_key_detected() -> None:
    hits = scan_secrets(f"OPENAI_API_KEY={_SK}")
    assert [h.kind for h in hits] == ["api_key"]
    start, end = hits[0].span
    assert f"OPENAI_API_KEY={_SK}"[start:end] == _SK


def test_aws_akia_key_detected() -> None:
    hits = scan_secrets(f"aws_access_key_id = {_AKIA}")
    assert [h.kind for h in hits] == ["aws_access_key"]
    start, end = hits[0].span
    assert f"aws_access_key_id = {_AKIA}"[start:end] == _AKIA


def test_jwt_token_detected() -> None:
    hits = scan_secrets(f"Cookie: session={_JWT};")
    assert [h.kind for h in hits] == ["jwt"]
    start, end = hits[0].span
    assert f"Cookie: session={_JWT};"[start:end] == _JWT


def test_private_key_header_detected() -> None:
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Q\n"
        "-----END RSA PRIVATE KEY-----"
    )
    hits = scan_secrets(f"key:\n{pem}\n")
    # The whole PEM block collapses to a single private_key hit (no stray blob).
    assert [h.kind for h in hits] == ["private_key"]
    start, end = hits[0].span
    assert f"key:\n{pem}\n"[start:end] == pem


def test_password_assignment_detected() -> None:
    hits = scan_secrets("db.password=hunter2!local")
    assert [h.kind for h in hits] == ["password_assignment"]
    start, end = hits[0].span
    # The span covers only the value, not the ``password=`` key.
    assert "db.password=hunter2!local"[start:end] == "hunter2!local"


def test_bearer_token_masks_only_the_token() -> None:
    text = "Authorization: Bearer aVeryLongOpaqueBearerToken123456"
    hits = scan_secrets(text)
    assert [h.kind for h in hits] == ["bearer"]
    start, end = hits[0].span
    assert text[start:end] == "aVeryLongOpaqueBearerToken123456"
    assert redact(text) == "Authorization: Bearer [REDACTED_BEARER]"


def test_clean_text_returns_empty() -> None:
    assert scan_secrets("Твёрдость сплава выросла после старения на 12%.") == []
    assert scan_secrets("just a short note, no secrets here") == []
    assert redact("hardness rose after aging") == "hardness rose after aging"


def test_redact_masks_all_hits() -> None:
    text = f"key={_SK} aws={_AKIA} jwt={_JWT} pw=password=secretpw"
    out = redact(text)
    # Every raw secret substring must be gone from the redacted output.
    for secret in (_SK, _AKIA, _JWT, "secretpw"):
        assert secret not in out
    # …and every detected span was replaced by its placeholder mask.
    for hit in scan_secrets(text):
        assert hit.redacted in out


def test_span_points_at_secret_exactly() -> None:
    text = f"prefix {_SK} suffix"
    hit = scan_secrets(text)[0]
    start, end = hit.span
    assert text[start:end] == _SK
    assert text[:start] == "prefix "
    assert text[end:] == " suffix"


def test_secret_hit_as_dict_shape() -> None:
    hit = scan_secrets(f"token {_JWT}")[0]
    assert isinstance(hit, SecretHit)
    payload = hit.as_dict()
    assert payload == {"kind": "jwt", "span": [6, 6 + len(_JWT)], "redacted": "[REDACTED_JWT]"}
    # span must serialize as a plain list (JSON-friendly), not a tuple.
    assert isinstance(payload["span"], list)


def test_multiple_secrets_sorted_and_non_overlapping() -> None:
    text = f"a={_AKIA} b={_SK} c={_JWT}"
    hits = scan_secrets(text)
    assert _kinds(text) == ["aws_access_key", "api_key", "jwt"]
    # Sorted by start offset and never overlapping.
    starts = [h.span[0] for h in hits]
    assert starts == sorted(starts)
    for earlier, later in pairwise(hits):
        assert earlier.span[1] <= later.span[0]


def test_sk_key_not_double_reported_as_base64() -> None:
    # The ``sk-`` tail is long enough to also match the base64 blob rule;
    # overlap resolution must keep exactly one, most-specific hit.
    assert _kinds(f"secret {_SK}") == ["api_key"]
