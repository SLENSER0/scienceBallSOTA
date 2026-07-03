"""LaTeX booktabs table export tests — экспорт таблицы в LaTeX (§22)."""

from __future__ import annotations

from kg_common.latex_table_export import (
    LatexTable,
    build_table,
    to_latex,
)


def test_two_columns_default_col_spec() -> None:
    # Assertion (1): two columns, no aligns -> col_spec == "ll" (both left).
    t = build_table([{"A": 1, "B": 2}], ["A", "B"])
    assert t.col_spec == "ll"


def test_header_line_rendered() -> None:
    # Assertion (2): the header row renders as `A & B \\`.
    t = build_table([], ["A", "B"])
    out = to_latex(t)
    assert r"A & B \\" in out.splitlines()


def test_percent_cell_escaped() -> None:
    # Assertion (3): a cell value "50%" renders as "50\%".
    t = build_table([{"A": "50%"}], ["A"])
    out = to_latex(t)
    assert r"50\%" in out
    assert "50%" not in out.replace(r"50\%", "")


def test_underscore_escaped() -> None:
    # Assertion (4): "a_b" -> "a\_b".
    t = build_table([{"A": "a_b"}], ["A"])
    out = to_latex(t)
    assert r"a\_b" in out


def test_missing_key_empty_cell() -> None:
    # Assertion (5): a column missing from a row -> empty cell in that row.
    t = build_table([{"A": "x"}], ["A", "B"])
    assert t.rows == (("x", ""),)
    out = to_latex(t)
    assert r"x &  \\" in out.splitlines()


def test_caption_adds_table_env() -> None:
    # Assertion (6): caption present adds \caption{...} and \begin{table}.
    t = build_table([{"A": "x"}], ["A"])
    out = to_latex(t, caption="My caption")
    assert r"\begin{table}" in out
    assert r"\caption{My caption}" in out


def test_no_caption_no_table_env() -> None:
    # Assertion (7): no caption/label -> no table env; starts with \begin{tabular}.
    t = build_table([{"A": "x"}], ["A"])
    out = to_latex(t)
    assert r"\begin{table}" not in out
    assert out.startswith(r"\begin{tabular}")


def test_aligns_override_col_spec() -> None:
    # Assertion (8): aligns={"B": "r"} yields col_spec "lr".
    t = build_table([{"A": 1, "B": 2}], ["A", "B"], aligns={"B": "r"})
    assert t.col_spec == "lr"


def test_booktabs_rules_present() -> None:
    # booktabs линейки: toprule/midrule/bottomrule all emitted, in order.
    t = build_table([{"A": "x"}], ["A"])
    lines = to_latex(t).splitlines()
    assert lines[0] == r"\begin{tabular}{l}"
    assert r"\toprule" in lines
    assert r"\midrule" in lines
    assert r"\bottomrule" in lines
    assert lines[1] == r"\toprule"
    assert lines[-2] == r"\bottomrule"
    assert lines[-1] == r"\end{tabular}"


def test_ampersand_hash_dollar_escaped() -> None:
    # Escaping of the remaining LaTeX-significant chars: & # $.
    t = build_table([{"A": "x&y #z $q"}], ["A"])
    out = to_latex(t)
    assert r"x\&y \#z \$q" in out


def test_as_dict_roundtrip() -> None:
    # as_dict() exposes columns/rows/col_spec as plain containers.
    t = build_table([{"A": "x", "B": "y"}], ["A", "B"], aligns={"B": "r"})
    assert t.as_dict() == {
        "columns": ["A", "B"],
        "rows": [["x", "y"]],
        "col_spec": "lr",
    }


def test_none_cell_empty() -> None:
    # An explicit None value renders as an empty cell, same as a missing key.
    t = build_table([{"A": None}], ["A"])
    assert t.rows == (("",),)


def test_frozen_dataclass() -> None:
    # LatexTable is frozen — неизменяемость.
    t = LatexTable(columns=("A",), rows=(("x",),), col_spec="l")
    try:
        t.col_spec = "r"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("LatexTable must be frozen")


def test_label_wraps_in_table_env() -> None:
    # label alone (no caption) still triggers the table env and \label{...}.
    t = build_table([{"A": "x"}], ["A"])
    out = to_latex(t, label="tab:metrics")
    assert r"\begin{table}" in out
    assert r"\label{tab:metrics}" in out
