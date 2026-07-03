"""Applicability-condition extraction/matching over a temp store (§24.14).

Hand-built graph (store API only — no seed/graph_store files touched):

- solution ``tech:ro`` has two applicability conditions forming a TDS window
  ``1.0 g/L <= tds_g_l <= 35.0 g/L`` (``ac:tds:1min`` with ``>=`` 1.0 and
  ``ac:tds:2max`` with ``<=`` 35.0), plus a temperature ceiling ``ac:temp`` with
  ``<=`` 40.0 °C;
- solution ``tech:bare`` has no applicability conditions.

The custom ``parameter`` / ``operator`` / ``value`` / ``note`` props are not Kuzu
columns, so the module reads them back through ``get_node``; ``unit`` is a base
column. Expected values below are checked by hand against this fixture.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.applicability import (
    ApplicabilityCondition,
    applicability_for,
    matches_context,
)
from kg_retrievers.graph_store import KuzuGraphStore

RO = "tech:ro"
BARE = "tech:bare"
AC_MIN = "ac:tds:1min"
AC_MAX = "ac:tds:2max"
AC_TEMP = "ac:temp"


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    s.upsert_node(RO, "TechnologySolution", name="Обратный осмос", domain="water_treatment")
    s.upsert_node(BARE, "TechnologySolution", name="Без условий", domain="water_treatment")
    s.upsert_node(
        AC_MIN,
        "ApplicabilityCondition",
        name="Минимальная солёность",
        parameter="tds_g_l",
        operator=">=",
        value=1.0,
        unit="g/L",
        note="ниже 1 г/л неэффективно",
    )
    s.upsert_node(
        AC_MAX,
        "ApplicabilityCondition",
        name="Максимальная солёность",
        parameter="tds_g_l",
        operator="<=",
        value=35.0,
        unit="g/L",
        note="выше 35 г/л нужен концентратор",
    )
    s.upsert_node(
        AC_TEMP,
        "ApplicabilityCondition",
        name="Температурный потолок",
        parameter="temp_c",
        operator="<=",
        value=40.0,
        unit="C",
    )
    s.upsert_edge(RO, AC_MIN, "HAS_APPLICABILITY_CONDITION", confidence=0.9)
    s.upsert_edge(RO, AC_MAX, "HAS_APPLICABILITY_CONDITION", confidence=0.9)
    s.upsert_edge(RO, AC_TEMP, "HAS_APPLICABILITY_CONDITION", confidence=0.8)
    yield s
    s.close()


def _by_id(store: KuzuGraphStore, solution_id: str) -> dict[str, ApplicabilityCondition]:
    return {c.condition_id: c for c in applicability_for(store, solution_id)}


def test_solution_with_condition_returns_it(store: KuzuGraphStore) -> None:
    conditions = applicability_for(store, RO)
    # three conditions, deterministically ordered by condition_id
    assert [c.condition_id for c in conditions] == [AC_MIN, AC_MAX, AC_TEMP]
    # custom props (not Kuzu columns) are resolved via get_node
    cmin = conditions[0]
    assert cmin.parameter == "tds_g_l"
    assert cmin.operator == ">="
    assert cmin.value == 1.0
    assert cmin.unit == "g/L"  # base column
    assert cmin.note == "ниже 1 г/л неэффективно"


def test_matches_context_true_when_in_range(store: KuzuGraphStore) -> None:
    conds = _by_id(store, RO)
    # tds_g_l = 5.0 satisfies both the >= 1.0 min and the <= 35.0 max
    assert matches_context(conds[AC_MIN], {"tds_g_l": 5.0}) is True
    assert matches_context(conds[AC_MAX], {"tds_g_l": 5.0}) is True
    # boundary is inclusive for >= / <=
    assert matches_context(conds[AC_MIN], {"tds_g_l": 1.0}) is True
    assert matches_context(conds[AC_MAX], {"tds_g_l": 35.0}) is True
    # a full context satisfies every RO condition
    ctx = {"tds_g_l": 10.0, "temp_c": 25.0}
    assert all(matches_context(c, ctx) for c in conds.values())


def test_matches_context_false_when_out_of_range(store: KuzuGraphStore) -> None:
    conds = _by_id(store, RO)
    # 0.5 g/L is below the >= 1.0 minimum
    assert matches_context(conds[AC_MIN], {"tds_g_l": 0.5}) is False
    # 50.0 g/L exceeds the <= 35.0 maximum
    assert matches_context(conds[AC_MAX], {"tds_g_l": 50.0}) is False
    # a parameter the context does not mention cannot be satisfied
    assert matches_context(conds[AC_TEMP], {"tds_g_l": 10.0}) is False
    # non-numeric / bool context values never pass (cannot be tested)
    assert matches_context(conds[AC_MIN], {"tds_g_l": "many"}) is False
    assert matches_context(conds[AC_MIN], {"tds_g_l": True}) is False


def test_multiple_conditions(store: KuzuGraphStore) -> None:
    conditions = applicability_for(store, RO)
    assert len(conditions) == 3
    # the TDS window is exactly [1.0, 35.0] and the temp ceiling is 40.0
    conds = {c.condition_id: c for c in conditions}
    assert (conds[AC_MIN].value, conds[AC_MAX].value) == (1.0, 35.0)
    assert conds[AC_TEMP].parameter == "temp_c"
    assert conds[AC_TEMP].value == 40.0
    # an operating point inside the window matches the pair but not blindly all
    in_window = {"tds_g_l": 20.0}
    passing = [c for c in conditions if matches_context(c, in_window)]
    assert {c.condition_id for c in passing} == {AC_MIN, AC_MAX}


def test_solution_without_conditions_returns_empty(store: KuzuGraphStore) -> None:
    assert applicability_for(store, BARE) == []


def test_unknown_solution_returns_empty(store: KuzuGraphStore) -> None:
    assert applicability_for(store, "tech:does-not-exist") == []


def test_as_dict(store: KuzuGraphStore) -> None:
    cmin = _by_id(store, RO)[AC_MIN]
    assert cmin.as_dict() == {
        "condition_id": AC_MIN,
        "parameter": "tds_g_l",
        "operator": ">=",
        "value": 1.0,
        "unit": "g/L",
        "note": "ниже 1 г/л неэффективно",
    }
    # a condition without a note serialises note as None
    ctemp = _by_id(store, RO)[AC_TEMP]
    assert ctemp.as_dict()["note"] is None
    assert ctemp.as_dict()["unit"] == "C"


def test_word_form_operators_match() -> None:
    # word-form operators resolve the same as their symbolic spellings
    cond = ApplicabilityCondition(
        condition_id="ac:x",
        parameter="throughput",
        operator="gte",
        value=100.0,
        unit="t/h",
        note=None,
    )
    assert matches_context(cond, {"throughput": 150.0}) is True
    assert matches_context(cond, {"throughput": 80.0}) is False
    # an unrecognised operator cannot be tested -> False
    bad = ApplicabilityCondition("ac:y", "throughput", "approx", 100.0, "t/h", None)
    assert matches_context(bad, {"throughput": 100.0}) is False
