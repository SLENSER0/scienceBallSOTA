"""Tests for §5.8 DocumentParser protocol + fallback orchestration.

Hand-checkable: fake parsers with known ``can_parse``/``parse`` behavior make
the fallback ordering, error collection and skip semantics fully deterministic.
The default parser is exercised against a real ``.txt`` temp file so the wrap of
:func:`ingestion_service.parsers.parse_document` is genuinely verified.
"""

from __future__ import annotations

from pathlib import Path

from ingestion_service.parser_protocol import (
    DefaultDocumentParser,
    DocumentParser,
    ParseError,
    ParseResult,
    default_parsers,
    get_parser,
    normalize_fmt,
    parse_with_fallback,
    parsed_doc_to_dict,
    register_parser,
    registered_parsers,
    unregister_parser,
)
from ingestion_service.parsers import parse_document


class _FakeParser:
    """Configurable stand-in parser (управляемый парсер) for orchestration tests."""

    def __init__(
        self,
        name: str,
        fmts: set[str],
        result: dict | None = None,
        *,
        raises: Exception | None = None,
    ) -> None:
        self.name = name
        self._fmts = fmts
        self._result = result
        self._raises = raises
        self.parse_calls = 0

    def can_parse(self, fmt: str) -> bool:
        return fmt in self._fmts

    def parse(self, path: str | Path) -> dict | None:
        self.parse_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._result


def test_registry_register_and_get_round_trip() -> None:
    parser = _FakeParser("fake-round-trip", {".x"})
    try:
        key = register_parser(parser)
        assert key == "fake-round-trip"
        assert get_parser("fake-round-trip") is parser
        assert "fake-round-trip" in registered_parsers()
        # explicit-name registration overrides the parser's own ``name``
        assert register_parser(parser, name="alias") == "alias"
        assert get_parser("alias") is parser
    finally:
        unregister_parser("fake-round-trip")
        unregister_parser("alias")
    assert get_parser("fake-round-trip") is None  # missing → None (не исключение)


def test_default_parser_registered_at_import() -> None:
    default = get_parser("default")
    assert isinstance(default, DefaultDocumentParser)
    assert default.name == "default"


def test_fallback_picks_first_that_can_parse_and_succeeds() -> None:
    doc = {"path": "b", "full_text": "ok"}
    a = _FakeParser("skip-a", set())  # can_parse False → skipped
    b = _FakeParser("win-b", {".x"}, result=doc)  # first to can_parse + succeed
    c = _FakeParser("never-c", {".x"}, result={"path": "c"})  # must not be reached

    res = parse_with_fallback("file.x", [a, b, c])

    assert res.ok is True
    assert res.parser == "win-b"
    assert res.doc is doc
    assert res.errors == ()  # a was skipped (not an error), b succeeded
    assert a.parse_calls == 0  # skipped parser never parses
    assert c.parse_calls == 0  # winner short-circuits the chain


def test_fallback_records_earlier_failures_then_succeeds() -> None:
    boom = _FakeParser("raiser", {".x"}, raises=ValueError("corrupt"))
    empty = _FakeParser("empty", {".x"}, result=None)  # soft failure (None)
    good = _FakeParser("good", {".x"}, result={"path": "z"})

    res = parse_with_fallback("file.x", [boom, empty, good])

    assert res.ok is True
    assert res.parser == "good"
    # both earlier failures are preserved, in order
    assert [e.parser for e in res.errors] == ["raiser", "empty"]
    assert "corrupt" in res.errors[0].message
    assert res.errors[1].message == "parser returned no document"


def test_all_fail_returns_ok_false_with_errors() -> None:
    a = _FakeParser("a", {".x"}, raises=RuntimeError("bad-a"))
    b = _FakeParser("b", {".x"}, result=None)

    res = parse_with_fallback("file.x", [a, b])

    assert res.ok is False
    assert res.parser is None
    assert res.doc is None
    assert len(res.errors) == 2
    assert {e.parser for e in res.errors} == {"a", "b"}


def test_unknown_format_is_skipped_without_error() -> None:
    # both parsers decline the format → nothing tried, no errors recorded
    a = _FakeParser("a", {".pdf"})
    b = _FakeParser("b", {".docx"})

    res = parse_with_fallback("file.zzz", [a, b])

    assert res.ok is False
    assert res.errors == ()  # skipped ≠ failed
    assert a.parse_calls == 0 and b.parse_calls == 0


def test_default_parser_wraps_parse_document_on_txt(tmp_path: Path) -> None:
    text = "Электроэкстракция никеля в диафрагменной ванне. Current density is high.\n"
    p = tmp_path / "report.txt"
    p.write_text(text, encoding="utf-8")

    parser = DefaultDocumentParser()
    assert parser.can_parse(".txt") is True
    doc = parser.parse(p)

    assert isinstance(doc, dict)
    assert doc["title"] == "report"  # == ParsedDoc.stem
    assert doc["path"] == str(p)
    assert "Электроэкстракция" in doc["full_text"]
    assert doc["pages"][0]["page"] == 1
    # dict mirrors the underlying ParsedDoc exactly
    reference = parse_document(p)
    assert reference is not None
    assert doc == parsed_doc_to_dict(reference)


def test_fallback_with_default_parser_end_to_end(tmp_path: Path) -> None:
    text = "This document is comfortably longer than the thirty character minimum.\n"
    p = tmp_path / "note.md"
    p.write_text(text, encoding="utf-8")

    res = parse_with_fallback(p, default_parsers())

    assert res.ok is True
    assert res.parser == "default"
    assert res.doc is not None
    assert res.doc["doc_type"]  # populated by parse_document
    assert res.errors == ()


def test_default_parser_returns_ok_false_for_unsupported_extension(tmp_path: Path) -> None:
    p = tmp_path / "data.zzz"
    p.write_text("some content that is long enough to exceed the minimum length\n")

    # DefaultDocumentParser declines the format, so the chain has nothing to try.
    res = parse_with_fallback(p, default_parsers())

    assert res.ok is False
    assert res.parser is None
    assert res.errors == ()  # skipped by can_parse, not a parse failure


def test_normalize_fmt_variants() -> None:
    assert normalize_fmt("pdf") == ".pdf"
    assert normalize_fmt(".PDF") == ".pdf"
    assert normalize_fmt("  .Txt ") == ".txt"
    assert normalize_fmt("report.DOCX") == ".docx"  # filename → suffix
    assert normalize_fmt("") == ""
    assert normalize_fmt("   ") == ""


def test_fmt_override_controls_can_parse_routing() -> None:
    # ``fmt`` overrides the format hint fed to ``can_parse`` (the path suffix is
    # ``.bin``, which the parser would otherwise decline).
    parser = _FakeParser("txt-only", {".txt"}, result={"path": "x"})

    without = parse_with_fallback("file.bin", [parser])
    assert without.ok is False  # ".bin" declined → skipped
    assert parser.parse_calls == 0

    forced = parse_with_fallback("file.bin", [parser], fmt=".txt")
    assert forced.ok is True  # override makes can_parse(".txt") succeed
    assert forced.parser == "txt-only"
    assert parser.parse_calls == 1


def test_parse_result_and_error_as_dict() -> None:
    err = ParseError("p1", "boom")
    assert err.as_dict() == {"parser": "p1", "message": "boom"}

    res = ParseResult(ok=True, parser="p1", doc={"path": "x"}, errors=(err,))
    d = res.as_dict()
    assert d == {
        "ok": True,
        "parser": "p1",
        "doc": {"path": "x"},
        "errors": [{"parser": "p1", "message": "boom"}],
    }
    # default ParseResult has an empty errors tuple
    assert ParseResult(ok=False).errors == ()


def test_default_parser_satisfies_protocol() -> None:
    assert isinstance(DefaultDocumentParser(), DocumentParser)
    assert isinstance(_FakeParser("x", set()), DocumentParser)

    class _NotAParser:
        pass

    assert not isinstance(_NotAParser(), DocumentParser)
