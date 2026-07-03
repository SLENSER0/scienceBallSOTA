"""§5.7/§5.11 parse cleanup — hand-checked de-hyphenation & soft-wrap cases (RU & EN)."""

from __future__ import annotations

from kg_extractors.text_reflow import (
    ReflowResult,
    dehyphenate,
    join_soft_wraps,
    reflow,
)


def test_dehyphenate_microstructure() -> None:
    assert dehyphenate("micro-\nstructure") == ("microstructure", 1)


def test_dehyphenate_well_known_count() -> None:
    joined, count = dehyphenate("well-\nknown")
    assert joined == "wellknown"
    assert count == 1


def test_dehyphenate_compound_untouched() -> None:
    # A genuine hyphenated compound (no ``-\n``) must not be joined.
    assert dehyphenate("state-of-the-art")[1] == 0
    assert dehyphenate("state-of-the-art")[0] == "state-of-the-art"


def test_dehyphenate_hyphen_space_not_joined() -> None:
    # Hyphen followed by a space, not a newline: left alone, count 0.
    assert dehyphenate("well- known") == ("well- known", 0)


def test_dehyphenate_cyrillic() -> None:
    assert dehyphenate("струк-\nтура") == ("структура", 1)


def test_dehyphenate_multiple() -> None:
    joined, count = dehyphenate("micro-\nstructure and struk-\ntура")
    assert count == 2
    assert joined == "microstructure and struktура"


def test_dehyphenate_leading_indent_on_wrap() -> None:
    # Indentation on the wrapped continuation line is swallowed by the join.
    assert dehyphenate("micro-\n    structure") == ("microstructure", 1)


def test_join_soft_wraps_single_newline() -> None:
    assert join_soft_wraps("a\nb") == ("a b", 1)


def test_join_soft_wraps_paragraph_break_kept() -> None:
    assert join_soft_wraps("a\n\nb") == ("a\n\nb", 0)


def test_join_soft_wraps_triple_newline_kept() -> None:
    assert join_soft_wraps("a\n\n\nb") == ("a\n\n\nb", 0)


def test_join_soft_wraps_mixed() -> None:
    collapsed, count = join_soft_wraps("line one\nline two\n\npara two\nstill")
    assert collapsed == "line one line two\n\npara two still"
    assert count == 2


def test_join_soft_wraps_no_newline() -> None:
    assert join_soft_wraps("no newline here") == ("no newline here", 0)


def test_reflow_dehyphenate_and_join() -> None:
    result = reflow("micro-\nstructure of\nthe alloy")
    assert result.text == "microstructure of the alloy"
    assert result.n_dehyphenated == 1
    assert result.n_joins == 1


def test_reflow_empty_as_dict() -> None:
    assert reflow("").as_dict() == {"text": "", "n_dehyphenated": 0, "n_joins": 0}


def test_reflow_cyrillic() -> None:
    result = reflow("струк-\nтура сплава")
    assert result.text == "структура сплава"
    assert result.n_dehyphenated == 1


def test_reflow_paragraph_break_preserved() -> None:
    result = reflow("first para line one\nline two\n\nsecond para")
    assert result.text == "first para line one line two\n\nsecond para"
    assert result.n_dehyphenated == 0
    assert result.n_joins == 1


def test_reflow_result_is_frozen() -> None:
    result = reflow("abc")
    assert isinstance(result, ReflowResult)
    try:
        result.text = "mutated"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("ReflowResult should be frozen")


def test_reflow_as_dict_roundtrip() -> None:
    result = reflow("micro-\nstructure of\nthe alloy")
    assert result.as_dict() == {
        "text": "microstructure of the alloy",
        "n_dehyphenated": 1,
        "n_joins": 1,
    }
