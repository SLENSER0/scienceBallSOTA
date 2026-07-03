"""Tests for §14.9 upload MIME/size pre-flight validation.

Проверяют allowlist MIME-типов, лимит 200 МБ и машинные причины отказа.
Exercise the MIME allowlist, the 200 MB ceiling and the machine reasons.
"""

from __future__ import annotations

from api_gateway.upload_validation import (
    ALLOWED_UPLOAD_TYPES,
    MAX_UPLOAD_BYTES,
    UploadCheck,
    is_allowed,
    sniff_media_type,
    validate_upload,
)


def test_max_upload_bytes_is_200_mib() -> None:
    assert MAX_UPLOAD_BYTES == 200 * 1024 * 1024


def test_allowlist_covers_expected_extensions() -> None:
    assert set(ALLOWED_UPLOAD_TYPES) == {"pdf", "docx", "txt", "csv", "md", "html"}
    assert ALLOWED_UPLOAD_TYPES["pdf"] == "application/pdf"


def test_valid_pdf_is_ok() -> None:
    check = validate_upload("a.pdf", "application/pdf", 1000)
    assert check.ok is True
    assert check.media_type == "application/pdf"
    assert check.reason is None
    assert check.size == 1000


def test_too_large_is_rejected() -> None:
    check = validate_upload("a.pdf", "application/pdf", MAX_UPLOAD_BYTES + 1)
    assert check.ok is False
    assert check.reason == "too_large"


def test_at_limit_is_ok() -> None:
    check = validate_upload("a.pdf", "application/pdf", MAX_UPLOAD_BYTES)
    assert check.ok is True
    assert check.reason is None


def test_unsupported_type_is_rejected() -> None:
    check = validate_upload("a.exe", "application/x-msdownload", 5)
    assert check.ok is False
    assert check.reason == "unsupported_type"


def test_empty_body_is_rejected() -> None:
    check = validate_upload("a.pdf", "application/pdf", 0)
    assert check.ok is False
    assert check.reason == "empty"


def test_empty_takes_precedence_over_type() -> None:
    # Пустое тело важнее типа / empty wins even for a bad type.
    check = validate_upload("a.exe", "application/x-msdownload", 0)
    assert check.reason == "empty"


def test_sniff_media_type_is_case_insensitive() -> None:
    assert sniff_media_type("X.PDF") == "application/pdf"
    assert sniff_media_type("report.Csv") == "text/csv"


def test_sniff_media_type_uses_basename() -> None:
    assert sniff_media_type("/tmp/dir.pdf/notes.md") == "text/markdown"


def test_sniff_media_type_unknown_and_missing_ext() -> None:
    assert sniff_media_type("a.exe") is None
    assert sniff_media_type("noext") is None


def test_is_allowed() -> None:
    assert is_allowed("application/pdf") is True
    assert is_allowed("application/zip") is False


def test_mismatched_declared_type_is_rejected() -> None:
    # Расширение из allowlist, но заявленный MIME чужой / bad declared MIME.
    check = validate_upload("a.pdf", "application/zip", 10)
    assert check.ok is False
    assert check.reason == "unsupported_type"


def test_as_dict_keys() -> None:
    check = validate_upload("a.pdf", "application/pdf", 1000)
    assert set(check.as_dict().keys()) == {"ok", "media_type", "size", "reason"}


def test_uploadcheck_is_frozen() -> None:
    check = UploadCheck(ok=True, media_type="application/pdf", size=1, reason=None)
    try:
        check.ok = False  # type: ignore[misc]
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("UploadCheck must be frozen")
