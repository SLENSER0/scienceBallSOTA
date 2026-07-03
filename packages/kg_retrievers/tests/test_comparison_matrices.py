"""Domain-specific comparison matrices over a hand-built temp store (§24.11).

The fixture builds a small, fully hand-checkable water-treatment (обессоливание)
slice directly through the store API — three desalination ``TechnologySolution``
methods with measured indicators, plus an off-domain method to prove scoping:

- reverse osmosis (RO): ``removal_efficiency`` measured twice (95.0 % and 97.0 %,
  so the *best* value is 97.0) and ``energy_consumption`` 3.5 kWh/m³; RO also has a
  ``HAS_APPLICABILITY_CONDITION`` node (условие применимости);
- ion exchange (IE): ``removal_efficiency`` 90.0 %, ``energy_consumption`` 1.2;
- electrodialysis (ED): ``removal_efficiency`` 88.0 %, ``energy_consumption`` 2.0;
- thermal distillation (DIST): a method with **no** measured indicator;
- nickel electrowinning (EW): an ``electrometallurgy`` method (off-domain).

The RO ``removal_efficiency`` measurements also carry a custom ``indicator_group``
prop (not a base Kuzu column) used to exercise the ``get_node`` read path.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.comparison_matrices import (
    ComparisonMatrix,
    MatrixCell,
    build_comparison,
    build_method_component_matrix,
)
from kg_retrievers.graph_store import KuzuGraphStore

RO = make_id("TechnologySolution", "reverse osmosis")
IE = make_id("TechnologySolution", "ion exchange")
ED = make_id("TechnologySolution", "electrodialysis")
DIST = make_id("TechnologySolution", "thermal distillation")
EW = make_id("TechnologySolution", "nickel electrowinning")
AC_RO = make_id("ApplicabilityCondition", "ro high tds")
EV_RO = make_id("Evidence", "desal-2022.pdf:ro-removal")

APPLIC_TEXT = "Подходит для TDS 1-35 г/л, требует предочистки"


def _method(store: KuzuGraphStore, mid: str, name: str, domain: str) -> None:
    store.upsert_node(mid, "TechnologySolution", name=name, domain=domain)


def _measure(
    store: KuzuGraphStore,
    key: str,
    prop: str,
    value: float,
    unit: str,
    method: str,
    *,
    evidence: list[str] | None = None,
    **extra: object,
) -> str:
    """Upsert a Measurement and link it to ``method`` via ABOUT_REGIME."""
    mid = make_id("Measurement", key)
    store.upsert_node(
        mid,
        "Measurement",
        name=key,
        property_name=prop,
        value_normalized=value,
        normalized_unit=unit,
        domain="water_treatment",
        **extra,
    )
    store.upsert_edge(mid, method, "ABOUT_REGIME", confidence=0.9, evidence_ids=evidence or [])
    return mid


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))

    _method(s, RO, "Обратный осмос (RO)", "water_treatment")
    _method(s, IE, "Ионный обмен", "water_treatment")
    _method(s, ED, "Электродиализ", "water_treatment")
    _method(s, DIST, "Термическая дистилляция", "water_treatment")
    _method(s, EW, "Электроэкстракция никеля", "electrometallurgy")

    # RO: two removal_efficiency measurements → best is 97.0; plus energy 3.5.
    # The custom ``indicator_group`` prop is stored in props JSON (not a base column).
    _measure(
        s, "ro removal low", "removal_efficiency", 95.0, "percent", RO, indicator_group="quality"
    )
    _measure(
        s,
        "ro removal high",
        "removal_efficiency",
        97.0,
        "percent",
        RO,
        evidence=[EV_RO],
        indicator_group="quality",
    )
    _measure(s, "ro energy", "energy_consumption", 3.5, "kWh/m3", RO, indicator_group="cost")
    # IE / ED single measurements.
    _measure(s, "ie removal", "removal_efficiency", 90.0, "percent", IE)
    _measure(s, "ie energy", "energy_consumption", 1.2, "kWh/m3", IE)
    _measure(s, "ed removal", "removal_efficiency", 88.0, "percent", ED)
    _measure(s, "ed energy", "energy_consumption", 2.0, "kWh/m3", ED)
    # Off-domain measurement on the electrowinning method (must not surface).
    _measure(s, "ew current", "current_density", 250.0, "A/m2", EW)

    # Applicability condition on RO only.
    s.upsert_node(AC_RO, "ApplicabilityCondition", name=APPLIC_TEXT, domain="water_treatment")
    s.upsert_edge(RO, AC_RO, "HAS_APPLICABILITY_CONDITION", confidence=0.9)

    yield s
    s.close()


@pytest.fixture
def empty_store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def test_matrix_has_method_rows_and_component_columns(store: KuzuGraphStore) -> None:
    m = build_method_component_matrix(store)
    assert isinstance(m, ComparisonMatrix)
    # rows are exactly the four in-domain methods (off-domain EW excluded), sorted
    assert set(m.rows) == {RO, IE, ED, DIST}
    assert EW not in m.rows
    # columns are the two measured indicators; the off-domain current_density is absent
    assert set(m.columns) == {"removal_efficiency", "energy_consumption"}
    assert "current_density" not in m.columns


def test_cell_carries_measured_value_and_evidence(store: KuzuGraphStore) -> None:
    m = build_method_component_matrix(store)
    cell = m.cell(RO, "removal_efficiency")
    assert isinstance(cell, MatrixCell)
    assert cell.value == 97.0
    assert cell.unit == "percent"
    assert cell.row == RO
    assert cell.column == "removal_efficiency"
    # evidence from the high-removal edge flows into the cell
    assert EV_RO in cell.evidence_ids
    # convenience accessor mirrors the cell value
    assert m.value(IE, "energy_consumption") == 1.2


def test_best_value_is_peak_of_multiple_measurements(store: KuzuGraphStore) -> None:
    # RO has removal_efficiency measured at 95.0 and 97.0 → the best (peak) is 97.0
    m = build_method_component_matrix(store)
    assert m.value(RO, "removal_efficiency") == 97.0
    # the source measurement id is the higher-value one
    cell = m.cell(RO, "removal_efficiency")
    assert cell is not None
    assert cell.measurement_id == make_id("Measurement", "ro removal high")


def test_applicability_captured_when_present(store: KuzuGraphStore) -> None:
    m = build_method_component_matrix(store)
    # RO has an applicability condition → every RO cell carries its text
    ro_cell = m.cell(RO, "removal_efficiency")
    assert ro_cell is not None
    assert ro_cell.applicability == APPLIC_TEXT
    assert m.cell(RO, "energy_consumption").applicability == APPLIC_TEXT
    # IE has no applicability condition → None
    assert m.cell(IE, "removal_efficiency").applicability is None


def test_method_without_measurements_is_a_row_with_no_cells(store: KuzuGraphStore) -> None:
    m = build_method_component_matrix(store)
    # DIST is a listed row but contributes no cells (no measured indicator)
    assert DIST in m.rows
    assert m.cell(DIST, "removal_efficiency") is None
    assert m.value(DIST, "energy_consumption") is None
    assert DIST not in m.cells


def test_empty_domain_yields_empty_rows(store: KuzuGraphStore, empty_store: KuzuGraphStore) -> None:
    # a domain that exists nowhere → no rows, no columns, no cells (graceful)
    absent = build_method_component_matrix(store, domain="no_such_domain")
    assert absent.rows == ()
    assert absent.columns == ()
    assert absent.cells == {}
    assert absent.is_empty
    # an empty graph is equally graceful
    empty = build_method_component_matrix(empty_store)
    assert empty.rows == ()
    assert empty.as_dict()["rows"] == []


def test_generic_build_comparison_by_property(store: KuzuGraphStore) -> None:
    # generic builder over a chosen base property = property_name (no applicability)
    m = build_comparison(
        store,
        row_label="TechnologySolution",
        col_property="property_name",
        domain="water_treatment",
    )
    assert set(m.columns) == {"removal_efficiency", "energy_consumption"}
    assert m.value(ED, "removal_efficiency") == 88.0
    # build_comparison never resolves applicability, even for RO
    assert m.cell(RO, "removal_efficiency").applicability is None


def test_generic_custom_property_read_via_get_node(store: KuzuGraphStore) -> None:
    # ``indicator_group`` is a custom prop (props JSON, not a base Kuzu column):
    # it is only reachable through get_node, which build_comparison uses.
    m = build_comparison(
        store,
        row_label="TechnologySolution",
        col_property="indicator_group",
        domain="water_treatment",
    )
    # only RO's measurements carry indicator_group → columns come from its two groups
    assert set(m.columns) == {"quality", "cost"}
    # the "quality" group aggregates both removal measurements → best is 97.0
    assert m.value(RO, "quality") == 97.0
    assert m.value(RO, "cost") == 3.5
    # methods without the custom prop contribute no cells
    assert m.cell(IE, "quality") is None


def test_deterministic_ordering(store: KuzuGraphStore) -> None:
    m = build_method_component_matrix(store)
    # rows and columns are sorted deterministically
    assert list(m.rows) == sorted(m.rows)
    assert list(m.columns) == sorted(m.columns)
    # rebuilding produces an identical serialisation
    assert build_method_component_matrix(store).as_dict() == m.as_dict()


def test_as_dict_shape_is_json_round_trippable(store: KuzuGraphStore) -> None:
    d = build_method_component_matrix(store).as_dict()
    assert set(d) == {"rows", "columns", "cells"}
    assert isinstance(d["rows"], list)
    assert isinstance(d["columns"], list)
    assert isinstance(d["cells"], dict)
    # nested cell dict exposes the §24.11 cell shape
    ro_cell = d["cells"][RO]["removal_efficiency"]
    assert ro_cell["value"] == 97.0
    assert ro_cell["applicability"] == APPLIC_TEXT
    assert set(ro_cell) == {
        "row",
        "column",
        "value",
        "unit",
        "applicability",
        "measurement_id",
        "evidence_ids",
    }
    # the whole payload survives a JSON round-trip
    assert json.loads(json.dumps(d))["cells"][RO]["removal_efficiency"]["value"] == 97.0
