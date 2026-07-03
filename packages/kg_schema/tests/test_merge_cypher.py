"""Hand-checked tests for per-label MERGE templates (§3.8).

Ожидаемые значения выведены вручную из реальных данных схемы: меток
:class:`kg_schema.labels.NodeLabel`, сигнатур :data:`kg_schema.relationships.EDGE_SCHEMA`
и раздела полей :mod:`kg_schema.merge_field_policy`.
"""

from __future__ import annotations

import pytest

from kg_schema.labels import NodeLabel
from kg_schema.merge_cypher import (
    MergeTemplate,
    all_node_templates,
    edge_merge_cypher,
    node_merge_cypher,
)
from kg_schema.merge_field_policy import PROTECTED_FIELDS


def test_material_node_merge_header() -> None:
    tpl = node_merge_cypher("Material", ["name", "aliases_text"])
    assert "MERGE (n:Material {id:$id})" in tpl.cypher


def test_node_merge_has_both_create_and_match_clauses() -> None:
    tpl = node_merge_cypher("Material", ["name", "aliases_text"])
    assert "ON CREATE SET" in tpl.cypher
    assert "ON MATCH SET" in tpl.cypher


def test_id_is_never_a_set_field() -> None:
    # id is written only via the MERGE key, never in ON CREATE / ON MATCH.
    tpl = node_merge_cypher("Material", ["id", "name", "aliases_text"])
    assert "id" not in tpl.on_create_fields
    assert "id" not in tpl.on_match_fields


def test_material_set_bodies_render_expected_fields() -> None:
    tpl = node_merge_cypher("Material", ["name", "aliases_text"])
    # name / aliases_text are neither protected nor create-only → in both clauses.
    assert tpl.on_create_fields == ("name", "aliases_text")
    assert tpl.on_match_fields == ("name", "aliases_text")
    assert "n.name = $name" in tpl.cypher
    assert "n.aliases_text = $aliases_text" in tpl.cypher


def test_protected_measurement_field_create_only() -> None:
    # 'value' is a PROTECTED_FIELD: written ON CREATE, excluded from ON MATCH.
    protected = PROTECTED_FIELDS[0]
    assert protected == "value"
    tpl = all_node_templates()["Measurement"]
    assert protected in tpl.on_create_fields
    assert protected not in tpl.on_match_fields


def test_measurement_on_match_keeps_updatable_fields() -> None:
    tpl = all_node_templates()["Measurement"]
    # 'unit' / 'updated_at' are ordinary updatable fields → survive ON MATCH.
    assert "unit" in tpl.on_match_fields
    assert "updated_at" in tpl.on_match_fields
    # every protected field is dropped from ON MATCH.
    for field in PROTECTED_FIELDS:
        assert field not in tpl.on_match_fields


def test_valid_edge_merge_contains_rel_and_run_key() -> None:
    # (Measurement, OF_PROPERTY, Property) is a declared EDGE_SCHEMA signature.
    cypher = edge_merge_cypher("Measurement", "OF_PROPERTY", "Property", ["confidence"])
    assert "OF_PROPERTY" in cypher
    assert "$extractor_run_id" in cypher
    assert "r.confidence = $confidence" in cypher


def test_edge_merge_has_directed_merge_and_matches() -> None:
    cypher = edge_merge_cypher("Measurement", "OF_PROPERTY", "Property", ["confidence"])
    assert "MATCH (a:Measurement {id:$from_id})" in cypher
    assert "MATCH (b:Property {id:$to_id})" in cypher
    assert "MERGE (a)-[r:OF_PROPERTY {extractor_run_id:$extractor_run_id}]->(b)" in cypher


def test_invalid_edge_signature_raises() -> None:
    # MENTIONS is only (Chunk, MENTIONS, Entity); Material->MENTIONS->Property is bogus.
    with pytest.raises(ValueError):
        edge_merge_cypher("Material", "MENTIONS", "Property", [])


def test_all_node_templates_cover_every_label() -> None:
    templates = all_node_templates()
    assert set(templates) == {str(label) for label in NodeLabel}
    assert all(isinstance(tpl, MergeTemplate) for tpl in templates.values())


def test_merge_template_as_dict() -> None:
    tpl = node_merge_cypher("Material", ["name", "aliases_text"])
    payload = tpl.as_dict()
    assert payload["label"] == "Material"
    assert payload["on_create_fields"] == ["name", "aliases_text"]
    assert payload["on_match_fields"] == ["name", "aliases_text"]
    assert "MERGE (n:Material {id:$id})" in payload["cypher"]
