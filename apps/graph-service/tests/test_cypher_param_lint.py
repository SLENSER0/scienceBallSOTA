"""Cypher template parameterization linter (§19.6)."""

from __future__ import annotations

from graph_service.cypher_param_lint import (
    ParamLintFinding,
    ParamLintReport,
    is_parameterized,
    lint_template,
)


def _kinds(report: ParamLintReport) -> list[str]:
    return [f.kind for f in report.findings]


def test_clean_parameterized_template_is_ok() -> None:
    # (1) fully parameterized: only ``$id``, no splicing → ok, no findings.
    report = lint_template("MATCH (n) WHERE n.id = $id RETURN n LIMIT 10")
    assert report.ok is True
    assert report.used_params == ("id",)
    assert report.findings == ()


def test_quoted_literal_filter_flagged() -> None:
    # (2) a hard-coded single-quoted RHS filter value is a violation.
    report = lint_template("MATCH (n) WHERE n.name = 'Al' RETURN n")
    assert report.ok is False
    assert "quoted_literal_filter" in _kinds(report)
    hit = next(f for f in report.findings if f.kind == "quoted_literal_filter")
    assert "'Al'" in hit.snippet


def test_brace_interpolation_flagged() -> None:
    # (3) a ``{doc_id}`` brace field is string interpolation.
    report = lint_template("MATCH (d:Node) WHERE d.id = {doc_id} RETURN d")
    assert report.ok is False
    assert "string_interp" in _kinds(report)


def test_printf_interpolation_flagged() -> None:
    report_s = lint_template("MATCH (n) WHERE n.id = %s RETURN n")
    report_named = lint_template("MATCH (n) WHERE n.id = %(x)s RETURN n")
    assert "string_interp" in _kinds(report_s)
    assert "string_interp" in _kinds(report_named)


def test_concat_flagged() -> None:
    # (4) a quoted literal glued to ``+`` is concatenation.
    report = lint_template("'a' + userval")
    assert report.ok is False
    assert "concat" in _kinds(report)


def test_fstring_prefix_flagged() -> None:
    report = lint_template('f"MATCH (n) WHERE n.id = {x} RETURN n"')
    assert "fstring" in _kinds(report)


def test_used_params_deduplicated() -> None:
    # (5) two ``$x`` occurrences collapse to a single sorted-unique entry.
    report = lint_template("MATCH (a)-[r]->(b) WHERE a.id = $x AND b.id = $x RETURN r")
    assert report.used_params == ("x",)


def test_used_params_sorted() -> None:
    report = lint_template("MATCH (n) WHERE n.a = $z AND n.b = $a RETURN n")
    assert report.used_params == ("a", "z")


def test_format_call_flagged() -> None:
    # (6) a ``.format(`` call is a format-based splice.
    report = lint_template('template.format(doc_id="x")')
    assert report.ok is False
    assert "format_call" in _kinds(report)


def test_is_parameterized_matches_report_ok() -> None:
    # (7) the convenience wrapper equals ``report.ok`` in both directions.
    clean = "MATCH (n) WHERE n.id = $id RETURN n"
    dirty = "MATCH (n) WHERE n.name = 'Al' RETURN n"
    assert is_parameterized(clean) is lint_template(clean).ok
    assert is_parameterized(dirty) is lint_template(dirty).ok
    assert is_parameterized(clean) is True
    assert is_parameterized(dirty) is False


def test_as_dict_findings_length_matches() -> None:
    # (8) serialized ``findings`` list length equals the number of findings.
    report = lint_template("MATCH (n) WHERE n.name = 'Al' RETURN n")
    payload = report.as_dict()
    assert len(payload["findings"]) == len(report.findings)


def test_finding_as_dict_roundtrips_fields() -> None:
    finding = ParamLintFinding(kind="concat", span=(0, 5), snippet="'a' +")
    assert finding.as_dict() == {
        "kind": "concat",
        "span": (0, 5),
        "snippet": "'a' +",
    }


def test_report_as_dict_shape() -> None:
    report = lint_template("MATCH (n) WHERE n.id = $id RETURN n")
    payload = report.as_dict()
    assert payload["ok"] is True
    assert payload["used_params"] == ["id"]
    assert payload["findings"] == []
    assert payload["template"] == "MATCH (n) WHERE n.id = $id RETURN n"


def test_findings_sorted_by_span() -> None:
    report = lint_template("MATCH (n) WHERE n.a = 'x' AND n.b = 'y' RETURN n")
    spans = [f.span for f in report.findings]
    assert spans == sorted(spans)
