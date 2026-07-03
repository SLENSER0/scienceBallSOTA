"""Gap export to CSV / JSON (§15.13).

Expected scores are hand-derivable from the gap-scoring weighted average
(absence 0.40, importance 0.25, domain 0.20, novelty 0.15; neutral default 0.5),
so a gap whose only signal is ``absence_confidence=a`` scores ``0.40*a + 0.30``.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from kg_retrievers.gap_export import (
    BASE_COLUMNS,
    GapExportTable,
    build_gap_export,
    gap_export_rows,
    gaps_to_csv,
    gaps_to_json,
)


def _parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Header list + row dicts, parsed back with the stdlib csv reader."""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    header = rows[0]
    dict_rows = [dict(zip(header, r, strict=True)) for r in rows[1:]]
    return header, dict_rows


def test_csv_has_header_then_one_line_per_gap() -> None:
    gaps = [
        {"gap_type": "a", "absence_confidence": 0.9},
        {"gap_type": "b", "absence_confidence": 0.4},
    ]
    out = gaps_to_csv(gaps)
    lines = out.splitlines()
    assert len(lines) == 3  # header + two data rows
    # BASE_COLUMNS first, then the shared extra key in first-seen order.
    assert lines[0] == "score,gap_type,domain,absence_confidence"
    header, dict_rows = _parse_csv(out)
    assert header == ["score", "gap_type", "domain", "absence_confidence"]
    assert [r["gap_type"] for r in dict_rows] == ["a", "b"]
    assert float(dict_rows[0]["score"]) == pytest.approx(0.66)  # 0.40*0.9 + 0.30
    assert float(dict_rows[1]["score"]) == pytest.approx(0.46)  # 0.40*0.4 + 0.30
    assert dict_rows[0]["domain"] == ""  # no domain → empty cell


def test_gaps_to_json_round_trips_to_export_rows() -> None:
    gaps = [{"gap_type": "a", "subject": "мембрана", "absence_confidence": 0.7}]
    text = gaps_to_json(gaps)
    loaded = json.loads(text)
    assert loaded == gap_export_rows(gaps)
    assert loaded[0]["subject"] == "мембрана"  # RU preserved verbatim
    assert loaded[0]["score"] == pytest.approx(0.58)  # 0.40*0.7 + 0.30


def test_export_rows_carry_the_priority_score() -> None:
    gap = {"gap_type": "g", "absence_confidence": 0.9}
    rows = gap_export_rows([gap])
    assert len(rows) == 1
    assert rows[0]["score"] == pytest.approx(0.66)  # 0.40*0.9 + 0.30
    assert rows[0]["gap_type"] == "g"
    assert rows[0]["domain"] == ""  # normalized: missing domain → empty string


def test_csv_preserves_russian_characters() -> None:
    gaps = [{"gap_type": "пробел", "subject": "полиамидная мембрана", "absence_confidence": 0.8}]
    out = gaps_to_csv(gaps)
    assert "полиамидная мембрана" in out
    assert "пробел" in out
    _, dict_rows = _parse_csv(out)
    assert dict_rows[0]["subject"] == "полиамидная мембрана"
    assert dict_rows[0]["gap_type"] == "пробел"


def test_missing_field_becomes_empty_cell() -> None:
    # Heterogeneous gaps: only the first has ``property``, only the second has
    # ``novelty`` — every row still spans the union of columns, blanks filled.
    gaps = [
        {"gap_type": "a", "absence_confidence": 0.9, "property": "проницаемость"},
        {"gap_type": "b", "novelty": 0.5},
    ]
    out = gaps_to_csv(gaps)
    header, dict_rows = _parse_csv(out)
    assert header == ["score", "gap_type", "domain", "absence_confidence", "property", "novelty"]
    # gap "b" has neither absence_confidence nor property → empty cells.
    assert dict_rows[1]["property"] == ""
    assert dict_rows[1]["absence_confidence"] == ""
    # gap "a" has no novelty → empty cell.
    assert dict_rows[0]["novelty"] == ""
    assert dict_rows[0]["property"] == "проницаемость"


def test_empty_gaps_yield_header_only() -> None:
    out = gaps_to_csv([])
    assert out == "score,gap_type,domain\n"
    assert out.splitlines() == ["score,gap_type,domain"]  # header, no data rows
    assert gap_export_rows([]) == []
    assert gaps_to_json([]) == "[]"


def test_columns_override_selects_and_orders_columns() -> None:
    gaps = [{"gap_type": "a", "subject": "мембрана", "absence_confidence": 0.9}]
    out = gaps_to_csv(gaps, columns=["subject", "score"])
    header, dict_rows = _parse_csv(out)
    assert header == ["subject", "score"]  # exactly the requested columns, in order
    assert list(dict_rows[0]) == ["subject", "score"]
    assert dict_rows[0]["subject"] == "мембрана"
    assert float(dict_rows[0]["score"]) == pytest.approx(0.66)


def test_base_columns_lead_the_default_header() -> None:
    gaps = [{"gap_type": "a", "owner": "лаб1", "absence_confidence": 0.5}]
    table = build_gap_export(gaps)
    assert table.columns[:3] == BASE_COLUMNS  # ("score", "gap_type", "domain")
    assert set(table.columns) == {"score", "gap_type", "domain", "owner", "absence_confidence"}


def test_export_table_as_dict_and_serializers_agree() -> None:
    gaps = [
        {"gap_type": "a", "subject": "цеолит", "absence_confidence": 0.7, "domain": "materials"}
    ]
    table = build_gap_export(gaps)
    assert isinstance(table, GapExportTable)
    dumped = table.as_dict()
    assert set(dumped) == {"columns", "rows"}
    assert dumped["rows"] == gap_export_rows(gaps)
    assert dumped["rows"][0]["domain"] == "materials"  # normalized, present
    # The table's own serializers match the module-level functions.
    assert table.to_csv() == gaps_to_csv(gaps)
    assert table.to_json() == gaps_to_json(gaps)
    # frozen dataclass: attributes cannot be reassigned.
    with pytest.raises(AttributeError):
        table.columns = ()  # type: ignore[misc]
