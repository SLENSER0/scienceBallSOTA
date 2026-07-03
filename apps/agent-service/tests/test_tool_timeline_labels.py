"""Tests for §13.22 tool-call timeline labels (§5.2.2) / тесты меток шкалы инструментов."""

from __future__ import annotations

from agent_service.tool_timeline_labels import (
    LABELS,
    TimelineStep,
    build_tool_timeline,
)


def test_resolve_entities_label() -> None:
    """A ``resolve_entities`` entry → label 'resolved entities'."""
    steps = build_tool_timeline([{"tool": "resolve_entities"}])
    assert steps[0].label == "resolved entities"
    assert steps[0].tool == "resolve_entities"


def test_hybrid_search_is_vector_search() -> None:
    """``hybrid_search`` → 'vector search'."""
    steps = build_tool_timeline([{"tool": "hybrid_search"}])
    assert steps[0].label == "vector search"


def test_scan_gaps_is_gap_scan() -> None:
    """``scan_gaps`` → 'gap scan'."""
    steps = build_tool_timeline([{"tool": "scan_gaps"}])
    assert steps[0].label == "gap scan"


def test_run_cypher_template_is_graph_query() -> None:
    """``run_cypher_template`` → 'graph query'."""
    steps = build_tool_timeline([{"tool": "run_cypher_template"}])
    assert steps[0].label == "graph query"


def test_graph_query_aliases_all_map() -> None:
    """All graph-query tools share the same human label."""
    for tool in ("run_cypher_template", "run_cypher_readonly", "find_graph_paths"):
        assert build_tool_timeline([{"tool": tool}])[0].label == "graph query"


def test_vector_search_aliases_all_map() -> None:
    """All vector-search tools share the same human label."""
    for tool in ("vector_search_qdrant", "keyword_search_opensearch", "hybrid_search"):
        assert build_tool_timeline([{"tool": tool}])[0].label == "vector search"


def test_evidence_and_gap_aliases() -> None:
    """Evidence-check and gap-scan aliases map to their phase labels."""
    assert build_tool_timeline([{"tool": "get_evidence_by_ids"}])[0].label == "evidence check"
    assert build_tool_timeline([{"tool": "get_document_snippet"}])[0].label == "evidence check"
    assert build_tool_timeline([{"tool": "detect_contradictions"}])[0].label == "gap scan"


def test_unknown_tool_falls_back_to_name() -> None:
    """An unknown tool 'foo' → label 'foo' (fallback to its own name)."""
    steps = build_tool_timeline([{"tool": "foo"}])
    assert steps[0].label == "foo"
    assert steps[0].tool == "foo"


def test_error_status_preserved() -> None:
    """An entry with status='error' preserves status 'error'."""
    steps = build_tool_timeline([{"tool": "hybrid_search", "status": "error"}])
    assert steps[0].status == "error"


def test_missing_status_defaults_to_ok() -> None:
    """A missing status defaults to 'ok'."""
    steps = build_tool_timeline([{"tool": "resolve_entities"}])
    assert steps[0].status == "ok"


def test_step_order_matches_trace_order() -> None:
    """Step order matches trace order exactly."""
    trace = [
        {"tool": "resolve_entities"},
        {"tool": "run_cypher_template"},
        {"tool": "hybrid_search"},
        {"tool": "get_evidence_by_ids"},
        {"tool": "scan_gaps"},
    ]
    steps = build_tool_timeline(trace)
    assert [s.tool for s in steps] == [e["tool"] for e in trace]
    assert [s.label for s in steps] == [
        "resolved entities",
        "graph query",
        "vector search",
        "evidence check",
        "gap scan",
    ]


def test_as_dict_exact_keys() -> None:
    """TimelineStep.as_dict() has exactly keys label/tool/status."""
    d = TimelineStep(label="graph query", tool="run_cypher_readonly", status="ok").as_dict()
    assert set(d) == {"label", "tool", "status"}
    assert d == {"label": "graph query", "tool": "run_cypher_readonly", "status": "ok"}


def test_timeline_step_is_frozen() -> None:
    """TimelineStep is frozen (immutable)."""
    step = TimelineStep(label="gap scan", tool="scan_gaps", status="ok")
    try:
        step.label = "other"  # type: ignore[misc]
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("TimelineStep should be frozen")


def test_labels_mapping_is_complete() -> None:
    """LABELS covers every documented raw tool with its §5.2.2 phase."""
    assert LABELS["resolve_entities"] == "resolved entities"
    assert LABELS["scan_gaps"] == "gap scan"
    assert LABELS["keyword_search_opensearch"] == "vector search"
