"""Tests for §24.13/§24.16 comparison-table JSON-LD export.

Real, hand-checkable assertions over a small technology-comparison table:
alternatives (rows) × criteria (columns), with measured cells, an evidence-bearing
cell, and gaps (explicit and by-omission). RU: тесты экспорта в JSON-LD.
"""

from __future__ import annotations

import json

from kg_retrievers.comparison_jsonld import (
    DEFAULT_CONTEXT_IRI,
    ComparisonJsonLd,
    comparison_to_jsonld,
)

# A tiny desalination-method comparison: two methods × three criteria.
ROWS = ["Reverse Osmosis", "Ion Exchange"]
COLS = ["removal_efficiency", "capex", "throughput"]
CELLS = {
    ("Reverse Osmosis", "removal_efficiency"): {
        "value": 99.0,
        "unit": "%",
        "evidence_ids": ["ev-1", "ev-2"],
    },
    ("Reverse Osmosis", "capex"): {"value": 1200.0, "unit": "USD/m3"},
    # ("Reverse Osmosis", "throughput") omitted -> gap by omission (assertion 6)
    ("Ion Exchange", "removal_efficiency"): {"value": 95.0, "unit": "%"},
    ("Ion Exchange", "capex"): {"gap": True},  # explicit gap (assertion 4)
    ("Ion Exchange", "throughput"): {"value": 40.0, "unit": "m3/h", "evidence_ids": []},
}


def _doc() -> dict:
    return comparison_to_jsonld(ROWS, COLS, CELLS)


def test_has_context_and_graph_keys() -> None:
    """(1) The document exposes both '@context' and '@graph'."""
    doc = _doc()
    assert "@context" in doc
    assert "@graph" in doc


def test_context_maps_each_criterion_to_iri() -> None:
    """@context maps every column key to a domain IRI derived from context_iri."""
    ctx = _doc()["@context"]
    assert set(ctx) == set(COLS)
    for col in COLS:
        assert ctx[col] == f"{DEFAULT_CONTEXT_IRI}{col}"


def test_graph_length_equals_rows() -> None:
    """(2) One node per row: len(@graph) == len(rows)."""
    assert len(_doc()["@graph"]) == len(ROWS)


def test_evidence_cell_keeps_evidence_ids() -> None:
    """(3) A cell with evidence keeps its evidence_ids list, value and unit."""
    ro = _doc()["@graph"][0]
    prop = ro["removal_efficiency"]
    assert prop["value"] == 99.0
    assert prop["unit"] == "%"
    assert prop["evidence_ids"] == ["ev-1", "ev-2"]
    assert "gap" not in prop


def test_explicit_gap_cell_has_gap_true_and_no_value() -> None:
    """(4) An explicit gap cell serializes as {'gap': True} with no value/unit."""
    ie = _doc()["@graph"][1]
    capex = ie["capex"]
    assert capex == {"gap": True}
    assert "value" not in capex
    assert "unit" not in capex


def test_missing_cell_becomes_gap() -> None:
    """(6) A (row, col) absent from cells is a gap in the output."""
    ro = _doc()["@graph"][0]
    assert ro["throughput"] == {"gap": True}


def test_node_id_is_deterministic_and_row_derived() -> None:
    """(5) Each @id derives deterministically from the row label."""
    doc_a = _doc()
    doc_b = _doc()
    ids_a = [n["@id"] for n in doc_a["@graph"]]
    ids_b = [n["@id"] for n in doc_b["@graph"]]
    assert ids_a == ids_b  # deterministic
    assert ids_a[0] == f"{DEFAULT_CONTEXT_IRI}reverse-osmosis"
    assert ids_a[1] == f"{DEFAULT_CONTEXT_IRI}ion-exchange"
    assert len(set(ids_a)) == len(ids_a)  # distinct rows -> distinct ids


def test_round_trips_through_json_dumps() -> None:
    """(7) The document round-trips through json.dumps/loads unchanged."""
    doc = _doc()
    reloaded = json.loads(json.dumps(doc))
    assert reloaded == doc


def test_empty_rows_yield_empty_graph() -> None:
    """(8) Empty rows -> empty @graph (context still reflects the columns)."""
    doc = comparison_to_jsonld([], COLS, {})
    assert doc["@graph"] == []
    assert set(doc["@context"]) == set(COLS)


def test_cell_without_evidence_gets_empty_list() -> None:
    """A measured cell lacking evidence still carries an empty evidence_ids list."""
    ie = _doc()["@graph"][1]
    eff = ie["removal_efficiency"]
    assert eff["evidence_ids"] == []
    assert eff["value"] == 95.0
    thr = ie["throughput"]
    assert thr["evidence_ids"] == []
    assert thr["value"] == 40.0


def test_custom_context_iri_is_used() -> None:
    """A caller-supplied context_iri drives both @context IRIs and node @ids."""
    base = "https://example.org/mine#"
    doc = comparison_to_jsonld(["Alt One"], ["k"], {}, context_iri=base)
    assert doc["@context"]["k"] == f"{base}k"
    assert doc["@graph"][0]["@id"] == f"{base}alt-one"


def test_as_dict_returns_independent_copies() -> None:
    """ComparisonJsonLd.as_dict yields fresh node dicts (mutation is isolated)."""
    obj = ComparisonJsonLd(context={"k": "iri"}, graph=({"@id": "x"},))
    first = obj.as_dict()
    first["@graph"][0]["@id"] = "mutated"
    assert obj.as_dict()["@graph"][0]["@id"] == "x"
