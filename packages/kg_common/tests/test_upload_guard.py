"""Tests for the upload validation guard — тесты проверки загрузок (§19.4)."""

from __future__ import annotations

import pytest

from kg_common.security.upload_guard import (
    UploadPolicy,
    UploadVerdict,
    sanitize_filename,
    validate_upload,
)

_PDF = "application/pdf"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _policy() -> UploadPolicy:
    return UploadPolicy(
        max_bytes=1_000_000,
        allowed_content_types=frozenset({_PDF, _DOCX}),
        magic_signatures={
            _PDF: (b"%PDF-",),
            _DOCX: (b"PK\x03\x04",),
        },
    )


def test_pdf_accepted() -> None:
    verdict = validate_upload(
        _policy(),
        filename="paper.pdf",
        declared_content_type=_PDF,
        head=b"%PDF-1.7",
        size=2048,
    )
    assert verdict.status == 200
    assert verdict.ok is True
    assert verdict.reason == "ok"


def test_too_large() -> None:
    policy = UploadPolicy(
        max_bytes=10,
        allowed_content_types=frozenset({_PDF}),
        magic_signatures={_PDF: (b"%PDF-",)},
    )
    verdict = validate_upload(
        policy,
        filename="paper.pdf",
        declared_content_type=_PDF,
        head=b"%PDF-1.7",
        size=99,
    )
    assert verdict.status == 413
    assert verdict.ok is False
    assert verdict.reason == "too_large"


def test_content_type_not_allowed() -> None:
    verdict = validate_upload(
        _policy(),
        filename="evil.bin",
        declared_content_type="text/x-evil",
        head=b"%PDF-1.7",
        size=32,
    )
    assert verdict.status == 415
    assert verdict.reason == "content_type"
    assert verdict.ok is False


def test_magic_mismatch() -> None:
    verdict = validate_upload(
        _policy(),
        filename="fake.pdf",
        declared_content_type=_PDF,
        head=b"PK\x03\x04",
        size=32,
    )
    assert verdict.status == 415
    assert verdict.reason == "magic_mismatch"
    assert verdict.ok is False


def test_docx_accepted() -> None:
    verdict = validate_upload(
        _policy(),
        filename="report.docx",
        declared_content_type=_DOCX,
        head=b"PK\x03\x04\x14\x00",
        size=4096,
    )
    assert verdict.ok is True
    assert verdict.status == 200


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("a\x00b.pdf", "ab.pdf"),
        ("/abs/path/report.pdf", "report.pdf"),
        ("C:\\Windows\\evil.exe", "evil.exe"),
        ("plain.pdf", "plain.pdf"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_verdict_as_dict_status_is_numeric() -> None:
    verdict = UploadVerdict(status=413, ok=False, reason="too_large", safe_filename="x.pdf")
    dumped = verdict.as_dict()
    assert dumped["status"] == 413
    assert dumped["status"] == verdict.status
    assert dumped == {
        "status": 413,
        "ok": False,
        "reason": "too_large",
        "safe_filename": "x.pdf",
    }


def test_policy_as_dict_roundtrip() -> None:
    dumped = _policy().as_dict()
    assert dumped["max_bytes"] == 1_000_000
    assert _PDF in dumped["allowed_content_types"]
    assert dumped["magic_signatures"][_PDF] == [b"%PDF-".hex()]
