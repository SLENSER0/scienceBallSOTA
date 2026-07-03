"""Extended §7.4 agent tools over a tiny hand-built graph (§13.6).

Deterministic, no LLM and no network: build a temp Kuzu store with a handful of
nodes/edges whose expected outputs are known by hand, then assert every new tool in
``agent_service.tools_ext`` returns the documented shape / values, that
``ALL_TOOL_NAMES`` is exactly the 16 §7.4 names, and that ``run_cypher_template``
refuses a mutating template.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from agent_service.tools import Tool
from agent_service.tools_ext import (
    ALL_TOOL_NAMES,
    CYPHER_TEMPLATES,
    EXTRA_TOOLS,
    SPEC_7_4_TOOL_NAMES,
    CypherTemplate,
    assert_read_only_cypher,
    create_review_task,
    detect_contradictions,
    expand_subgraph,
    find_graph_paths,
    get_document_snippet,
    get_experiment_table,
    hybrid_search,
    keyword_search,
    resolve_entities,
    run_cypher_template,
    search_material_aliases,
    vector_search,
)

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore

# -- known ids of the tiny graph ------------------------------------------
WATER = make_id("Material", "mine water")
RO = make_id("Method", "reverse osmosis desalination")
SALINITY = make_id("Property", "salinity")
MEAS_A = make_id("Measurement", "flow velocity a")
MEAS_B = make_id("Measurement", "flow velocity b")
MEAS_SAL = make_id("Measurement", "salinity reduction")
EV = make_id("Evidence", "ro-2020:p3")
DOC = "ro-2020.pdf"


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    """A tiny, fully hand-checkable graph (§13.6 test fixture)."""
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    # Entities (all §3.4 ENTITY_LABELS → projected by graph_algos / alias index).
    s.upsert_node(
        WATER,
        "Material",
        name="Mine water",
        canonical_name="mine water",
        aliases_text="process water|оборотная вода",
        material_class="water",
        domain="water_treatment",
        text="mine process water feed for desalination",
    )
    s.upsert_node(
        RO,
        "Method",
        name="Reverse osmosis desalination",
        canonical_name="reverse osmosis",
        aliases_text="RO|обратный осмос",
        domain="water_treatment",
        text="reverse osmosis membrane desalination removes salinity from mine process water",
    )
    s.upsert_node(
        SALINITY, "Property", name="Salinity", canonical_name="salinity", domain="water_treatment"
    )
    # Two conflicting flow-velocity measurements (0.2 vs 0.5 m/s → divergence 0.6).
    s.upsert_node(
        MEAS_A,
        "Measurement",
        name="flow velocity (ru)",
        property_name="flow_velocity",
        value_normalized=0.2,
        normalized_unit="m/s",
        confidence=0.9,
        domain="electrometallurgy",
        evidence_strength="peer_reviewed",
    )
    s.upsert_node(
        MEAS_B,
        "Measurement",
        name="flow velocity (foreign)",
        property_name="flow_velocity",
        value_normalized=0.5,
        normalized_unit="m/s",
        confidence=0.7,
        domain="electrometallurgy",
        evidence_strength="internal_report",
    )
    # An experiment measurement wired to material + method + evidence.
    s.upsert_node(
        MEAS_SAL,
        "Measurement",
        name="salinity reduction",
        property_name="salinity",
        value_normalized=95.0,
        normalized_unit="%",
        confidence=0.88,
        domain="water_treatment",
        effect_direction="decrease",
    )
    s.upsert_node(
        EV,
        "Evidence",
        doc_id=DOC,
        page=3,
        evidence_strength="peer_reviewed",
        confidence=0.9,
        text="reverse osmosis reduced salinity by 95% in mine water treatment",
    )
    # Edges: entity path Material—Method—Property + measurement provenance.
    s.upsert_edge(WATER, RO, "USED_IN", confidence=0.9)
    s.upsert_edge(RO, SALINITY, "MEASURES", confidence=0.9)
    s.upsert_edge(MEAS_SAL, WATER, "ABOUT_MATERIAL", confidence=0.9)
    s.upsert_edge(MEAS_SAL, RO, "ABOUT_REGIME", confidence=0.9)
    s.upsert_edge(MEAS_SAL, EV, "SUPPORTED_BY", confidence=0.9, evidence_ids=[EV])
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Registry: exactly the 16 §7.4 names
# ---------------------------------------------------------------------------
def test_all_tool_names_is_the_spec_16() -> None:
    assert len(ALL_TOOL_NAMES) == 16
    assert len(set(ALL_TOOL_NAMES)) == 16  # unique
    assert set(ALL_TOOL_NAMES) == set(SPEC_7_4_TOOL_NAMES)


def test_extra_tools_are_tool_descriptors() -> None:
    assert len(EXTRA_TOOLS) == 12
    assert all(isinstance(t, Tool) for t in EXTRA_TOOLS)
    names = {t.name for t in EXTRA_TOOLS}
    assert names <= set(SPEC_7_4_TOOL_NAMES)
    # the four base names are covered elsewhere, not re-implemented here
    assert "get_evidence_by_ids" not in names
    assert "run_cypher_readonly" not in names


def test_extra_tool_run_adapter(store: KuzuGraphStore) -> None:
    tool = next(t for t in EXTRA_TOOLS if t.name == "find_graph_paths")
    out = tool.run(store, {"source_id": WATER, "target_id": SALINITY})
    assert out["found"] is True
    assert out["paths"] == [[WATER, RO, SALINITY]]


# ---------------------------------------------------------------------------
# Entity resolution + material aliases
# ---------------------------------------------------------------------------
def test_resolve_entities_exact(store: KuzuGraphStore) -> None:
    out = resolve_entities(store, mentions=["process water"])
    assert out["count"] == 1
    m = out["mentions"][0]
    assert m["entity_id"] == WATER
    assert m["confidence"] == 1.0  # exact alias hit
    assert any(c["entity_id"] == WATER for c in m["candidates"])


def test_search_material_aliases(store: KuzuGraphStore) -> None:
    out = search_material_aliases(store, name="process water")
    ids = [m["entity_id"] for m in out["matches"]]
    assert WATER in ids
    # only material-family labels survive the default filter (the Method is excluded)
    assert RO not in ids
    assert all(m["label"] == "Material" for m in out["matches"])


# ---------------------------------------------------------------------------
# run_cypher_template: reads + read-only guard
# ---------------------------------------------------------------------------
def test_run_cypher_template_reads(store: KuzuGraphStore) -> None:
    out = run_cypher_template(store, template_name="nodes_by_label", params={"label": "Method"})
    assert out["count"] >= 1
    assert RO in [r[0] for r in out["rows"]]


def test_run_cypher_template_measurements(store: KuzuGraphStore) -> None:
    out = run_cypher_template(
        store, template_name="measurements_by_property", params={"property": "flow_velocity"}
    )
    ids = {r[0] for r in out["rows"]}
    assert ids == {MEAS_A, MEAS_B}


def test_run_cypher_template_rejects_mutating(store: KuzuGraphStore) -> None:
    evil = {"evil": CypherTemplate("evil", "MATCH (n:Node) DETACH DELETE n RETURN count(n)")}
    with pytest.raises(ValueError, match="mutating"):
        run_cypher_template(store, template_name="evil", templates=evil)
    # the store is untouched — the write never executed
    assert store.get_node(WATER) is not None


def test_run_cypher_template_unknown_raises(store: KuzuGraphStore) -> None:
    with pytest.raises(ValueError, match="unknown"):
        run_cypher_template(store, template_name="does_not_exist")


def test_assert_read_only_guard() -> None:
    assert_read_only_cypher("MATCH (n:Node) RETURN n.id")  # ok, no raise
    for bad in ("MATCH (n) DELETE n", "MERGE (a:Node {id:'x'})", "MATCH (n) SET n.x=1"):
        with pytest.raises(ValueError, match="mutating"):
            assert_read_only_cypher(bad)


def test_cypher_templates_are_all_read_only() -> None:
    for tmpl in CYPHER_TEMPLATES.values():
        assert_read_only_cypher(tmpl.cypher)  # must not raise


# ---------------------------------------------------------------------------
# Search family: keyword / vector / hybrid
# ---------------------------------------------------------------------------
def test_keyword_search_hits(store: KuzuGraphStore) -> None:
    out = keyword_search(store, query="osmosis desalination", top_k=5)
    assert out["backend"] == "bm25"
    ids = [h["id"] for h in out["hits"]]
    assert out["count"] >= 1
    assert RO in ids
    assert all(h["score"] > 0 for h in out["hits"])


def test_vector_search_hits(store: KuzuGraphStore) -> None:
    out = vector_search(store, query="reverse osmosis desalination", top_k=5)
    assert out["mode"] == "sparse"
    ids = [h["id"] for h in out["hits"]]
    assert RO in ids


def test_hybrid_search_hits(store: KuzuGraphStore) -> None:
    out = hybrid_search(store, query="osmosis desalination", top_k=5)
    assert out["backend"] == "hybrid_rrf"
    ids = [h["id"] for h in out["hits"]]
    assert RO in ids
    assert out["count"] >= 1


# ---------------------------------------------------------------------------
# Evidence / experiment / snippet
# ---------------------------------------------------------------------------
def test_get_experiment_table(store: KuzuGraphStore) -> None:
    out = get_experiment_table(store, filters={"domain": "water_treatment"})
    assert out["columns"] == [
        "id",
        "material",
        "processing",
        "property",
        "value",
        "unit",
        "effect",
        "confidence",
        "evidence_ids",
    ]
    assert out["count"] == 1
    row = out["rows"][0]
    assert row["id"] == MEAS_SAL
    assert row["material"] == "Mine water"
    assert row["processing"] == "Reverse osmosis desalination"
    assert row["property"] == "salinity"
    assert row["value"] == 95.0
    assert row["effect"] == "decrease"
    assert EV in row["evidence_ids"]


def test_get_document_snippet(store: KuzuGraphStore) -> None:
    out = get_document_snippet(store, doc_id=DOC, page=3)
    assert out["found"] is True
    assert out["page"] == 3
    assert "salinity" in out["snippet"]


def test_get_document_snippet_span(store: KuzuGraphStore) -> None:
    out = get_document_snippet(store, doc_id=DOC, span=[0, 7])
    assert out["snippet"] == "reverse"


def test_get_document_snippet_missing(store: KuzuGraphStore) -> None:
    out = get_document_snippet(store, doc_id="nope.pdf")
    assert out["found"] is False
    assert out["snippet"] == ""


# ---------------------------------------------------------------------------
# Graph traversal: paths + subgraph
# ---------------------------------------------------------------------------
def test_find_graph_paths(store: KuzuGraphStore) -> None:
    out = find_graph_paths(store, source_id=WATER, target_id=SALINITY, max_hops=4)
    assert out["found"] is True
    assert out["paths"] == [[WATER, RO, SALINITY]]
    assert out["hops"] == 2


def test_find_graph_paths_respects_max_hops(store: KuzuGraphStore) -> None:
    out = find_graph_paths(store, source_id=WATER, target_id=SALINITY, max_hops=1)
    assert out["found"] is False
    assert out["paths"] == []


def test_expand_subgraph(store: KuzuGraphStore) -> None:
    out = expand_subgraph(store, node_ids=[WATER], depth=1)
    ids = {n["id"] for n in out["nodes"]}
    assert WATER in ids and RO in ids
    assert out["node_count"] >= 2
    assert out["edge_count"] >= 1


# ---------------------------------------------------------------------------
# Contradictions + review task
# ---------------------------------------------------------------------------
def test_detect_contradictions(store: KuzuGraphStore) -> None:
    out = detect_contradictions(store, property="flow_velocity")
    assert out["count"] == 1
    c = out["contradictions"][0]
    assert {c["a_id"], c["b_id"]} == {MEAS_A, MEAS_B}
    assert c["subtype"] == "numeric_divergence"
    assert c["severity"] >= 0.3
    # peer_reviewed side wins over internal_report (§3.6)
    assert c["likely_correct"] == "a"


def test_create_review_task(store: KuzuGraphStore) -> None:
    out = create_review_task(
        store,
        target_type="Measurement",
        target_id=MEAS_A,
        reason="contradiction",
        payload={"note": "flow velocity conflict"},
    )
    assert out["status"] == "open"
    assert out["target_exists"] is True
    assert out["priority"] == 1.0
    assert out["payload"] == {"note": "flow velocity conflict"}
    # deterministic id (idempotent re-emit)
    again = create_review_task(
        store, target_type="Measurement", target_id=MEAS_A, reason="contradiction"
    )
    assert again["task_id"] == out["task_id"]


def test_create_review_task_unknown_target(store: KuzuGraphStore) -> None:
    out = create_review_task(
        store, target_type="Measurement", target_id="meas:ghost", reason="low_confidence"
    )
    assert out["target_exists"] is False
    assert out["priority"] == 1.0  # low_confidence is a high-priority trigger
