"""Structured comparison-report builder tests (§24.16 / §24.13).

Hand-checked against a two-solution fixture with two metrics (capex / opex):

- solution A (``sol:a``) carries evidence-backed capex (5.0 MUSD, ev:1+ev:2) and
  opex (1.2 MUSD/год, ev:2);
- solution B (``sol:b``) carries evidence-backed capex (3.0 MUSD, ev:2+ev:3) but is
  *missing* opex → a gap cell;
- so the deduped sources across all value cells are {ev:1, ev:2, ev:3}, and the only
  gap is (sol:b, opex).
"""

from __future__ import annotations

from kg_retrievers.report_builder import (
    GAP_DASH,
    GAP_KEY,
    SOLUTION_HEADER,
    SOURCES_HEADER,
    ComparisonReport,
    build_comparison_report,
    to_markdown,
)

METRICS = ["capex", "opex"]

SOLUTIONS: list[dict] = [
    {
        "id": "sol:a",
        "name": "Решение A",
        "metrics": {
            "capex": {"value": 5.0, "unit": "MUSD", "evidence_ids": ["ev:2", "ev:1"]},
            "opex": {"value": 1.2, "unit": "MUSD/год", "evidence_ids": ["ev:2"]},
        },
    },
    {
        "id": "sol:b",
        "name": "Решение B",
        "metrics": {
            "capex": {"value": 3.0, "unit": "MUSD", "evidence_ids": ["ev:3", "ev:2"]},
            # opex intentionally absent → gap
        },
    },
]


def _report() -> ComparisonReport:
    return build_comparison_report(SOLUTIONS, METRICS)


def test_every_cell_is_evidence_backed_or_gap() -> None:
    # §24.13 invariant: no cell is ever empty — value cells carry evidence, gaps flag.
    report = _report()
    assert report.columns == ("capex", "opex")
    assert len(report.rows) == 2
    for row in report.rows:
        assert len(row.cells) == len(METRICS)
        for cell in row.cells:
            d = cell.as_dict()
            if cell.is_gap:
                assert d == {GAP_KEY: True}
            else:
                # value cell must be evidence-backed (never empty evidence)
                assert cell.evidence_ids
                assert set(d) == {"value", "unit", "evidence_ids"}
                assert d["evidence_ids"]


def test_missing_metric_becomes_gap_cell() -> None:
    # sol:b has no opex entry → its opex cell is a gap, serialising to {gap: True}.
    report = _report()
    row_b = next(r for r in report.rows if r.solution_id == "sol:b")
    opex_cell = next(c for c in row_b.cells if c.metric == "opex")
    assert opex_cell.is_gap is True
    assert opex_cell.as_dict() == {GAP_KEY: True}
    # its capex, in contrast, is an evidence-backed value cell
    capex_cell = next(c for c in row_b.cells if c.metric == "capex")
    assert capex_cell.is_gap is False
    assert capex_cell.value == 3.0


def test_value_without_evidence_becomes_gap() -> None:
    # §24.13: a value present but with NO supporting evidence is not a real cell.
    sols = [
        {
            "id": "sol:c",
            "name": "Решение C",
            "metrics": {
                "capex": {"value": 9.0, "unit": "MUSD", "evidence_ids": []},
                "opex": {"value": None, "unit": "MUSD/год", "evidence_ids": ["ev:9"]},
            },
        }
    ]
    report = build_comparison_report(sols, METRICS)
    row = report.rows[0]
    # value-but-no-evidence → gap; evidence-but-no-value → gap
    assert all(c.is_gap for c in row.cells)
    assert report.sources == ()
    assert len(report.gaps) == 2


def test_to_markdown_table_shape() -> None:
    # header row + separator + one row per solution + a gap dash + Sources section.
    report = _report()
    md = to_markdown(report)
    lines = md.splitlines()

    assert lines[0] == f"| {SOLUTION_HEADER} | capex | opex |"
    assert lines[1] == "| --- | --- | --- |"

    blank_idx = lines.index("")
    data_rows = lines[2:blank_idx]
    assert len(data_rows) == len(SOLUTIONS)  # exactly one row per solution
    assert data_rows[0].startswith("| Решение A |")
    assert data_rows[1].startswith("| Решение B |")
    # the missing opex renders as the gap dash in solution B's row
    assert data_rows[1].endswith(f"| {GAP_DASH} |")
    assert data_rows[0].count(GAP_DASH) == 0  # solution A has no gaps

    assert f"## {SOURCES_HEADER}" in lines
    assert "- ev:1" in lines


def test_sources_deduped() -> None:
    # ev:2 is cited by three separate value cells but appears once, sorted.
    report = _report()
    assert report.sources == ("ev:1", "ev:2", "ev:3")
    assert len(report.sources) == len(set(report.sources))
    assert report.as_dict()["sources"] == ["ev:1", "ev:2", "ev:3"]


def test_empty_solutions_yields_empty_report_with_columns() -> None:
    report = build_comparison_report([], METRICS)
    assert report.columns == ("capex", "opex")
    assert report.rows == ()
    assert report.sources == ()
    assert report.gaps == ()
    d = report.as_dict()
    assert d["columns"] == ["capex", "opex"]
    assert d["rows"] == []
    # markdown still has the header + a dash-only sources section
    md = to_markdown(report)
    assert md.splitlines()[0] == f"| {SOLUTION_HEADER} | capex | opex |"
    assert f"- {GAP_DASH}" in md.splitlines()


def test_gaps_list_collects_gap_cells() -> None:
    # exactly the (sol:b, opex) pair is a gap across the whole table.
    report = _report()
    assert len(report.gaps) == 1
    gap = report.gaps[0]
    assert (gap.solution_id, gap.metric) == ("sol:b", "opex")
    assert gap.as_dict() == {
        "solution_id": "sol:b",
        "solution_name": "Решение B",
        "metric": "opex",
        GAP_KEY: True,
    }
    # the gaps list and the table's gap cells agree in count
    table_gaps = [c for r in report.rows for c in r.cells if c.is_gap]
    assert len(table_gaps) == len(report.gaps)


def test_as_dict_round_trip() -> None:
    report = _report()
    d = report.as_dict()
    rebuilt = ComparisonReport.from_dict(d)
    # dict → object → dict is stable, and the object itself is reconstructed intact
    assert rebuilt.as_dict() == d
    assert rebuilt == report
    assert set(d) == {"columns", "rows", "sources", "gaps"}
