"""Hand-checked tests for §3.19 edge-dict relation validation.

Every signature below is copied verbatim from a real entry in
:data:`kg_schema.relationships.EDGE_SCHEMA`, so the expected values are hand-verifiable:
``(Person, MEMBER_OF, Lab)`` and ``(Person, MEMBER_OF, ResearchTeam)`` are declared, while
``(Person, MEMBER_OF, Person)`` is not; ``(Material, HAS_COMPOSITION, Composition)`` is
declared. ``Person`` has exactly four outgoing signatures: two ``MEMBER_OF`` and two
``EXPERT_IN`` (to ``Material`` / ``ProcessingRegime``).
"""

from __future__ import annotations

from kg_schema.relation_validation import (
    RelationValidation,
    allowed_relations_from,
    validate_relation,
)


def test_valid_relation_passes() -> None:
    # (Person, MEMBER_OF, Lab) is a declared signature.
    result = validate_relation(
        {"source_label": "Person", "rel_type": "MEMBER_OF", "target_label": "Lab"}
    )
    assert isinstance(result, RelationValidation)
    assert result.ok is True
    assert result.reason == ""


def test_second_valid_relation_passes() -> None:
    # (Material, HAS_COMPOSITION, Composition) is declared.
    result = validate_relation(
        {
            "source_label": "Material",
            "rel_type": "HAS_COMPOSITION",
            "target_label": "Composition",
        }
    )
    assert result.ok is True
    assert result.reason == ""


def test_bad_target_reason_names_allowed_set() -> None:
    # Person MEMBER_OF Person is not declared; only Lab / ResearchTeam are targets.
    result = validate_relation(
        {"source_label": "Person", "rel_type": "MEMBER_OF", "target_label": "Person"}
    )
    assert result.ok is False
    assert "invalid target 'Person'" in result.reason
    assert "Person-[:MEMBER_OF]->" in result.reason
    assert "Lab" in result.reason
    assert "ResearchTeam" in result.reason


def test_unknown_rel_type_reason() -> None:
    result = validate_relation(
        {"source_label": "Document", "rel_type": "NOPE_REL", "target_label": "Section"}
    )
    assert result.ok is False
    assert result.reason == "unknown rel_type: 'NOPE_REL'"


def test_allowed_relations_from_returns_schema_set() -> None:
    # Person has exactly four declared outgoing signatures (sorted pairs).
    assert allowed_relations_from("Person") == [
        ("EXPERT_IN", "Material"),
        ("EXPERT_IN", "ProcessingRegime"),
        ("MEMBER_OF", "Lab"),
        ("MEMBER_OF", "ResearchTeam"),
    ]
    # An unknown source label has no outgoing relations.
    assert allowed_relations_from("Banana") == []


def test_as_dict_shape() -> None:
    ok_result = validate_relation(
        {"source_label": "Person", "rel_type": "MEMBER_OF", "target_label": "Lab"}
    )
    assert ok_result.as_dict() == {"ok": True, "reason": ""}
    bad_result = validate_relation(
        {"source_label": "Person", "rel_type": "MEMBER_OF", "target_label": "Person"}
    )
    d = bad_result.as_dict()
    assert d["ok"] is False
    assert d["reason"] == bad_result.reason


def test_missing_field_error() -> None:
    # target_label absent → reported as the first (and only) missing field.
    result = validate_relation({"source_label": "Person", "rel_type": "MEMBER_OF"})
    assert result.ok is False
    assert result.reason == "missing required field: 'target_label'"
    # A blank source_label is also treated as missing.
    blank = validate_relation(
        {"source_label": "  ", "rel_type": "MEMBER_OF", "target_label": "Lab"}
    )
    assert blank.ok is False
    assert blank.reason == "missing required field: 'source_label'"


def test_entity_target_expansion_validates() -> None:
    # (Chunk, MENTIONS, Entity) expands to concrete ENTITY_LABELS, so Material passes.
    good = validate_relation(
        {"source_label": "Chunk", "rel_type": "MENTIONS", "target_label": "Material"}
    )
    assert good.ok is True
    # Section is not an Entity, so it is an invalid MENTIONS target.
    bad = validate_relation(
        {"source_label": "Chunk", "rel_type": "MENTIONS", "target_label": "Section"}
    )
    assert bad.ok is False
    assert "invalid target 'Section'" in bad.reason


def test_source_without_outgoing_relation() -> None:
    # PERFORMED_BY is a known rel_type, but Lab is never its source.
    result = validate_relation(
        {"source_label": "Lab", "rel_type": "PERFORMED_BY", "target_label": "Person"}
    )
    assert result.ok is False
    assert result.reason == "'Lab' has no outgoing PERFORMED_BY relation"


def test_relation_validation_is_frozen() -> None:
    result = validate_relation(
        {"source_label": "Person", "rel_type": "MEMBER_OF", "target_label": "Lab"}
    )
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.ok = False  # type: ignore[misc]
