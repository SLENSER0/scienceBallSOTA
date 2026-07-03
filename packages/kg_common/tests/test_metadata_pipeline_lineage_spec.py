"""Tests for the canonical §9.1 pipeline lineage spec (§10.5).

Hand-checkable assertions over the fixed twelve-step ingestion DAG — проверяемые
вручную тесты канонического пайплайна.
"""

from __future__ import annotations

from kg_common.metadata.pipeline_lineage_spec import (
    PIPELINE_STEPS,
    StepSpec,
    lineage_edges,
    missing_steps,
    terminal_outputs,
)


def test_twelve_steps_with_unique_names() -> None:
    """Exactly twelve steps, all names unique — двенадцать уникальных шагов."""
    assert len(PIPELINE_STEPS) == 12
    names = [step.name for step in PIPELINE_STEPS]
    assert len(set(names)) == 12
    assert "neo4j_upsert" in names


def test_expected_canonical_names_in_dag_order() -> None:
    """Step names match the §9.1 DAG exactly, in order — порядок шагов §9.1."""
    assert [step.name for step in PIPELINE_STEPS] == [
        "register_source",
        "docling_parse",
        "store_parsed_s3",
        "chunk",
        "extract",
        "normalize_units",
        "entity_resolution",
        "validate_schema",
        "neo4j_upsert",
        "qdrant_index",
        "opensearch_index",
        "gap_scan",
    ]


def test_stepspec_as_dict_roundtrip() -> None:
    """``StepSpec.as_dict`` returns plain lists — сериализация в словарь."""
    step = StepSpec("extract", ("chunks",), ("extracted_triples",))
    assert step.as_dict() == {
        "name": "extract",
        "inputs": ["chunks"],
        "outputs": ["extracted_triples"],
    }


def test_terminal_outputs_are_the_three_serving_stores() -> None:
    """Terminals are exactly the three stores — три терминальных выхода."""
    terminals = terminal_outputs()
    assert terminals == {"neo4j_kg", "qdrant_index", "opensearch_index"}
    assert len(terminals) == 3


def test_lineage_edges_contain_chunk_to_extract() -> None:
    """The chunks -> extracted_triples edge is present — ребро линиджа."""
    edges = lineage_edges()
    assert ("chunks", "extracted_triples") in edges


def test_lineage_edges_are_sorted_and_deduplicated() -> None:
    """Edges are sorted and free of duplicates — сортировка и дедупликация."""
    edges = lineage_edges()
    assert edges == sorted(edges)
    assert len(edges) == len(set(edges))


def test_lineage_edges_full_expected_set() -> None:
    """The full deterministic edge set matches the DAG — весь набор рёбер."""
    assert lineage_edges() == [
        ("chunks", "extracted_triples"),
        ("chunks", "opensearch_index"),
        ("chunks", "qdrant_index"),
        ("extracted_triples", "normalized_triples"),
        ("normalized_triples", "resolved_entities"),
        ("parsed_doc", "parsed_s3_ref"),
        ("parsed_s3_ref", "chunks"),
        ("resolved_entities", "validated_graph"),
        ("source_record", "parsed_doc"),
        ("validated_graph", "neo4j_kg"),
    ]


def test_missing_steps_with_one_emitted() -> None:
    """One emitted step leaves eleven missing — одиннадцать пропущенных."""
    missing = missing_steps(["register_source"])
    assert len(missing) == 11
    assert "register_source" not in missing


def test_missing_steps_empty_when_all_emitted() -> None:
    """No missing steps when every name is emitted — все шаги учтены."""
    assert missing_steps([step.name for step in PIPELINE_STEPS]) == ()


def test_missing_steps_preserves_canonical_order() -> None:
    """Missing steps follow canonical DAG order — канонический порядок."""
    missing = missing_steps(["chunk", "extract"])
    assert missing[0] == "register_source"
    assert "chunk" not in missing
    assert "extract" not in missing
