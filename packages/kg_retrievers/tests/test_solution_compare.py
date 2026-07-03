"""Side-by-side solution comparison over a temp graph (§24.24).

Hand-built store (no seed). Two solutions link measurement nodes carrying a
``property_name`` + ``value_normalized`` (+ ``normalized_unit``):

- A ``tech:sol-a`` measures TDS twice (1500 and 1200 mg/L -> peak 1500), recovery 85 %, and
  links a non-measurement ``Gap`` that must be ignored.
- B ``tech:sol-b`` measures TDS once (800 mg/L) and never measures recovery -> a blank cell.

Every asserted value is checkable by hand from these numbers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.solution_compare import ComparisonTable, compare_solutions

SOL_A = "tech:sol-a"
SOL_B = "tech:sol-b"


def _new_store() -> KuzuGraphStore:
    return KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    s = _new_store()
    # A: TDS measured twice (peak 1500), recovery once, plus a non-measurement Gap link
    s.upsert_node(SOL_A, "TechnologySolution", name="Solution A (решение А)")
    s.upsert_node(
        "m-a-tds1",
        "Measurement",
        property_name="TDS",
        value_normalized=1500.0,
        normalized_unit="mg/L",
    )
    s.upsert_node(
        "m-a-tds2",
        "Measurement",
        property_name="TDS",
        value_normalized=1200.0,
        normalized_unit="mg/L",
    )
    s.upsert_node(
        "m-a-rec",
        "Measurement",
        property_name="recovery",
        value_normalized=85.0,
        normalized_unit="%",
    )
    s.upsert_node("gap-a", "Gap", name="not a measurement")
    for dst in ("m-a-tds1", "m-a-tds2", "m-a-rec", "gap-a"):
        s.upsert_edge(SOL_A, dst, "HAS_MEASUREMENT", confidence=0.9)

    # B: TDS once (800), no recovery
    s.upsert_node(SOL_B, "TechnologySolution", name="Solution B (решение Б)")
    s.upsert_node(
        "m-b-tds",
        "Measurement",
        property_name="TDS",
        value_normalized=800.0,
        normalized_unit="mg/L",
    )
    s.upsert_edge(SOL_B, "m-b-tds", "HAS_MEASUREMENT")

    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    s = _new_store()
    yield s
    s.close()


def test_two_solutions_compared(store: KuzuGraphStore) -> None:
    table = compare_solutions(store, [SOL_A, SOL_B])
    # both solutions are columns, in input order; the Gap link contributes no row
    assert table.solutions == (SOL_A, SOL_B)
    assert table.rows == ("TDS", "recovery")
    assert not table.is_empty


def test_property_values(store: KuzuGraphStore) -> None:
    table = compare_solutions(store, [SOL_A, SOL_B])
    assert table.value("TDS", SOL_A) == 1500.0
    assert table.value("TDS", SOL_B) == 800.0
    assert table.value("recovery", SOL_A) == 85.0
    # B never measured recovery -> no cell -> None
    assert table.value("recovery", SOL_B) is None
    # units and provenance ride along on the cell
    cell = table.cell("TDS", SOL_A)
    assert cell is not None
    assert cell.unit == "mg/L"
    assert cell.measurement_id == "m-a-tds1"


def test_peak_value_per_property(store: KuzuGraphStore) -> None:
    table = compare_solutions(store, [SOL_A])
    # A measured TDS at 1500 and 1200 -> the peak (1500) wins, from m-a-tds1
    assert table.value("TDS", SOL_A) == 1500.0
    assert table.cell("TDS", SOL_A).measurement_id == "m-a-tds1"  # type: ignore[union-attr]


def test_missing_value_blank(store: KuzuGraphStore) -> None:
    d = compare_solutions(store, [SOL_A, SOL_B]).as_dict()
    # the dense grid renders B's absent recovery as a blank string
    assert d["cells"]["recovery"][SOL_B] == ""
    # A's recovery is a full cell, not blank
    assert d["cells"]["recovery"][SOL_A]["value"] == 85.0


def test_property_filter(store: KuzuGraphStore) -> None:
    table = compare_solutions(store, [SOL_A, SOL_B], property="TDS")
    # scoping to one property drops the recovery row
    assert table.rows == ("TDS",)
    assert table.value("TDS", SOL_A) == 1500.0
    # a property no compared solution measured yields an empty table
    empty = compare_solutions(store, [SOL_A, SOL_B], property="no_such_prop")
    assert empty.rows == ()
    assert empty.is_empty


def test_single_solution(store: KuzuGraphStore) -> None:
    table = compare_solutions(store, [SOL_A])
    assert table.solutions == (SOL_A,)
    assert table.rows == ("TDS", "recovery")
    assert table.value("recovery", SOL_A) == 85.0


def test_unknown_id(store: KuzuGraphStore) -> None:
    # an id that resolves to no node is dropped; the known one still compares
    table = compare_solutions(store, [SOL_A, "tech:does-not-exist"])
    assert table.solutions == (SOL_A,)
    assert table.value("TDS", SOL_A) == 1500.0
    # an all-unknown / empty id list is graceful -> fully empty table
    assert compare_solutions(store, ["nope"]).solutions == ()
    assert compare_solutions(store, []).rows == ()


def test_as_dict_shape(store: KuzuGraphStore) -> None:
    d = compare_solutions(store, [SOL_A, SOL_B]).as_dict()
    assert set(d) == {"solutions", "rows", "cells"}
    assert d["solutions"] == [SOL_A, SOL_B]
    assert d["rows"] == ["TDS", "recovery"]
    # every row is dense over every solution column
    for prop in d["rows"]:
        assert set(d["cells"][prop]) == {SOL_A, SOL_B}
    # a populated cell exposes the full JSON cell shape
    tds_a = d["cells"]["TDS"][SOL_A]
    assert tds_a == {
        "solution": SOL_A,
        "property": "TDS",
        "value": 1500.0,
        "unit": "mg/L",
        "measurement_id": "m-a-tds1",
    }


def test_empty_store(empty_store: KuzuGraphStore) -> None:
    # nothing to compare in a fresh graph
    table = compare_solutions(empty_store, [SOL_A, SOL_B])
    assert table.solutions == ()
    assert table.rows == ()
    assert table.as_dict() == {"solutions": [], "rows": [], "cells": {}}


def test_returns_comparison_table(store: KuzuGraphStore) -> None:
    assert isinstance(compare_solutions(store, [SOL_A]), ComparisonTable)
