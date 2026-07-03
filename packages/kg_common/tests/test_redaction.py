"""Tests for secret/PII redaction (§19.7)."""

from __future__ import annotations

from kg_common.security import redact, redact_mapping


def test_bearer_token_keeps_last4() -> None:
    # 36-char token; last four chars are "7890".
    text = "Authorization: Bearer abcDEF123456ghijklmnopqrstuvwXYZ7890"
    out = redact(text)
    assert out == "Authorization: Bearer ***7890"
    assert "abcDEF123456" not in out


def test_email_partial_keeps_domain() -> None:
    assert redact("a@example.com") == "***@example.com"
    assert redact("ping bob@corp.io now") == "ping ***@corp.io now"


def test_openai_sk_key_masked() -> None:
    # sk- + 40 chars; last four of the tail are "6789".
    key = "sk-abcdefghij0123456789abcdefghij0123456789"
    out = redact(f"key={key}")
    assert out == "key=sk-***6789"
    assert "abcdefghij" not in out


def test_jwt_masked() -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    out = redact(f"token {jwt} end")
    assert out == "token [REDACTED_JWT] end"
    assert jwt not in out


def test_connection_string_password_masked() -> None:
    dsn = "postgres://kguser:S3cretPass@db.host:5432/kg"
    out = redact(dsn)
    assert out == "postgres://kguser:***@db.host:5432/kg"
    assert "S3cretPass" not in out


def test_hex_blob_masked() -> None:
    blob = "deadbeef" * 5  # 40 hex chars, tail "beef"
    out = redact(f"digest={blob}")
    assert out == "digest=***beef"
    assert blob not in out


def test_dict_password_key_redacted() -> None:
    out = redact_mapping({"user": "alice", "password": "hunter2"})
    assert out == {"user": "alice", "password": "***"}


def test_nested_list_and_dict() -> None:
    data = {
        "level": "info",
        "creds": {"password": "hunter2", "token": "abc123"},
        "users": [
            {"email": "bob@corp.io", "role": "admin"},
            "plain message",
        ],
        "retries": 3,
    }
    out = redact_mapping(data)
    assert out["level"] == "info"
    assert out["creds"] == {"password": "***", "token": "***"}
    assert out["users"][0] == {"email": "***@corp.io", "role": "admin"}
    assert out["users"][1] == "plain message"
    assert out["retries"] == 3


def test_plain_text_unchanged() -> None:
    text = "The quick brown fox jumps over 13 lazy dogs."
    assert redact(text) == text


def test_input_dict_not_mutated() -> None:
    data = {"api_key": "sk-secretsecretsecretsecret", "items": ["a@b.com"]}
    out = redact_mapping(data)
    # Original is untouched...
    assert data == {"api_key": "sk-secretsecretsecretsecret", "items": ["a@b.com"]}
    # ...while the copy is redacted.
    assert out["api_key"] == "***"
    assert out["items"] == ["***@b.com"]
    assert out is not data
