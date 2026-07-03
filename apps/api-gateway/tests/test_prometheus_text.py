"""Тесты рендера Prometheus-экспозиции для ``/admin/metrics`` (§14.11).

Tests for the Prometheus text-exposition renderer: escaping, single-sample
rendering, header ordering, integer-value formatting and the trailing newline.
"""

from __future__ import annotations

from api_gateway.prometheus_text import (
    MetricFamily,
    Sample,
    escape_label_value,
    render_exposition,
    render_family,
)


def test_escape_label_value_backslash_and_quote() -> None:
    # a"b\c  ->  a\"b\\c
    assert escape_label_value('a"b\\c') == 'a\\"b\\\\c'


def test_escape_label_value_newline() -> None:
    assert escape_label_value("a\nb") == "a\\nb"


def test_sample_with_labels_renders_with_braces() -> None:
    fam = MetricFamily("http_req", "counter", "reqs", (Sample("http_req", 5.0, {"route": "/x"}),))
    out = render_family(fam)
    assert 'http_req{route="/x"} 5' in out


def test_sample_without_labels_renders_bare() -> None:
    fam = MetricFamily("http_req", "counter", "reqs", (Sample("http_req", 5.0),))
    out = render_family(fam)
    assert "http_req 5" in out
    assert "{" not in out.splitlines()[-1] if out.splitlines() else True


def test_render_family_header_ordering() -> None:
    fam = MetricFamily("http_req", "counter", "reqs", ())
    out = render_family(fam)
    assert out.startswith("# HELP http_req reqs\n# TYPE http_req counter\n")


def test_render_exposition_ends_with_newline() -> None:
    fam = MetricFamily("http_req", "counter", "reqs", (Sample("http_req", 5.0),))
    assert render_exposition([fam]).endswith("\n") is True


def test_integer_valued_float_has_no_decimal() -> None:
    fam = MetricFamily("g", "gauge", "h", (Sample("g", 42.0),))
    assert "g 42\n" in render_family(fam)


def test_non_integer_float_keeps_decimal() -> None:
    fam = MetricFamily("g", "gauge", "h", (Sample("g", 1.5),))
    assert "g 1.5\n" in render_family(fam)


def test_label_value_escaped_in_output() -> None:
    fam = MetricFamily("m", "gauge", "h", (Sample("m", 1.0, {"k": 'a"b'}),))
    out = render_family(fam)
    assert 'm{k="a\\"b"} 1' in out


def test_multiple_labels_sorted_deterministically() -> None:
    fam = MetricFamily("m", "gauge", "h", (Sample("m", 1.0, {"b": "2", "a": "1"}),))
    out = render_family(fam)
    assert 'm{a="1",b="2"} 1' in out


def test_render_exposition_joins_families() -> None:
    fam1 = MetricFamily("a", "counter", "ha", (Sample("a", 1.0),))
    fam2 = MetricFamily("b", "gauge", "hb", (Sample("b", 2.0),))
    out = render_exposition([fam1, fam2])
    assert out == "# HELP a ha\n# TYPE a counter\na 1\n# HELP b hb\n# TYPE b gauge\nb 2\n"


def test_as_dict_roundtrip() -> None:
    s = Sample("m", 3.0, {"k": "v"})
    assert s.as_dict() == {"name": "m", "value": 3.0, "labels": {"k": "v"}}
    fam = MetricFamily("m", "gauge", "h", (s,))
    assert fam.as_dict() == {
        "name": "m",
        "type": "gauge",
        "help": "h",
        "samples": [{"name": "m", "value": 3.0, "labels": {"k": "v"}}],
    }
