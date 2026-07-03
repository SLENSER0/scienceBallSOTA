"""Tests for §14.9 download/export Content-Disposition + media type."""

from __future__ import annotations

from api_gateway.content_disposition import (
    Disposition,
    content_disposition,
    export_headers,
    media_type_for,
    safe_filename,
)


def test_safe_filename_strips_traversal() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"


def test_safe_filename_replaces_unsafe_chars() -> None:
    # basename of "a b/c?.csv" is "c?.csv"; "?" → "_".
    assert safe_filename("a b/c?.csv") == "c_.csv"


def test_safe_filename_keeps_safe_chars() -> None:
    assert safe_filename("Run_01.data-2.json") == "Run_01.data-2.json"


def test_safe_filename_replaces_spaces() -> None:
    assert safe_filename("my report.csv") == "my_report.csv"


def test_content_disposition_default_attachment() -> None:
    assert content_disposition("x.csv") == 'attachment; filename="x.csv"'


def test_content_disposition_inline() -> None:
    value = content_disposition("x.csv", inline=True)
    assert value.startswith("inline;")
    assert value == 'inline; filename="x.csv"'


def test_content_disposition_sanitises_name() -> None:
    assert content_disposition("../a b.csv") == 'attachment; filename="a_b.csv"'


def test_media_type_known() -> None:
    assert media_type_for("csv") == "text/csv"
    assert media_type_for("json") == "application/json"
    assert media_type_for("md") == "text/markdown"
    assert media_type_for("pdf") == "application/pdf"
    assert media_type_for("png") == "image/png"


def test_media_type_unknown_falls_back() -> None:
    assert media_type_for("zzz") == "application/octet-stream"


def test_media_type_case_and_dot_insensitive() -> None:
    assert media_type_for(".CSV") == "text/csv"
    assert media_type_for("JSON") == "application/json"


def test_export_headers_keys() -> None:
    assert set(export_headers("x.json")) == {"Content-Disposition", "Content-Type"}


def test_export_headers_infers_content_type() -> None:
    assert export_headers("x.json")["Content-Type"] == "application/json"


def test_export_headers_default_attachment() -> None:
    headers = export_headers("report.csv")
    assert headers["Content-Type"] == "text/csv"
    assert headers["Content-Disposition"] == 'attachment; filename="report.csv"'


def test_export_headers_explicit_media_type_wins() -> None:
    headers = export_headers("x.bin", media_type="application/zip")
    assert headers["Content-Type"] == "application/zip"


def test_export_headers_inline() -> None:
    headers = export_headers("x.png", inline=True)
    assert headers["Content-Type"] == "image/png"
    assert headers["Content-Disposition"].startswith("inline;")


def test_export_headers_unknown_extension() -> None:
    assert export_headers("archive.tar")["Content-Type"] == "application/octet-stream"


def test_disposition_dataclass_is_frozen() -> None:
    d = Disposition(filename="x.csv", media_type="text/csv", inline=False)
    assert d.as_dict() == {
        "filename": "x.csv",
        "media_type": "text/csv",
        "inline": False,
    }
    assert d.header_value() == 'attachment; filename="x.csv"'


def test_disposition_inline_header_value() -> None:
    d = Disposition(filename="doc.pdf", media_type="application/pdf", inline=True)
    assert d.header_value() == 'inline; filename="doc.pdf"'
