"""Hand-checked tests for edge-signature validation (§3.16).

All signatures below are copied from real entries in
:data:`kg_schema.relationships.EDGE_SCHEMA`, so expected values are hand-verifiable.
"""

from __future__ import annotations

import pytest

from kg_schema.edge_guard import (
    EdgeSignature,
    EdgeSignatureError,
    allowed_targets,
    is_allowed_signature,
    validate_edge_signature,
)


def test_valid_signature_passes() -> None:
    # (Document, HAS_SECTION, Section) is a declared structural edge.
    assert validate_edge_signature("Document", "HAS_SECTION", "Section") is None
    assert is_allowed_signature("Document", "HAS_SECTION", "Section") is True


def test_second_valid_signature_passes() -> None:
    # (Person, MEMBER_OF, Lab) and (Material, HAS_COMPOSITION, Composition).
    assert validate_edge_signature("Person", "MEMBER_OF", "Lab") is None
    assert validate_edge_signature("Material", "HAS_COMPOSITION", "Composition") is None


def test_invalid_target_raises() -> None:
    # Person MEMBER_OF Person is not declared (only Lab / ResearchTeam are).
    with pytest.raises(EdgeSignatureError) as exc:
        validate_edge_signature("Person", "MEMBER_OF", "Person")
    assert isinstance(exc.value, ValueError)
    assert exc.value.allowed == ("Lab", "ResearchTeam")


def test_unknown_rel_type_raises() -> None:
    with pytest.raises(EdgeSignatureError) as exc:
        validate_edge_signature("Document", "NOPE_REL", "Section")
    # No signature declares NOPE_REL, so there are no allowed targets.
    assert exc.value.allowed == ()


def test_unknown_from_label_raises() -> None:
    with pytest.raises(EdgeSignatureError) as exc:
        validate_edge_signature("Banana", "HAS_SECTION", "Section")
    assert exc.value.allowed == ()


def test_allowed_targets_returns_schema_set() -> None:
    # Document HAS_SECTION targets both Section and Table in the schema.
    assert allowed_targets("Document", "HAS_SECTION") == ["Section", "Table"]
    # Person MEMBER_OF targets Lab and ResearchTeam.
    assert allowed_targets("Person", "MEMBER_OF") == ["Lab", "ResearchTeam"]


def test_allowed_targets_empty_for_unknown() -> None:
    assert allowed_targets("Person", "NOT_A_REL") == []
    assert allowed_targets("NotALabel", "MEMBER_OF") == []


def test_is_allowed_signature_bool_matches() -> None:
    assert is_allowed_signature("Person", "MEMBER_OF", "Lab") is True
    assert is_allowed_signature("Person", "MEMBER_OF", "Person") is False


def test_error_message_names_signature_and_hint() -> None:
    with pytest.raises(EdgeSignatureError) as exc:
        validate_edge_signature("Person", "MEMBER_OF", "Person")
    msg = str(exc.value)
    assert "Person-[:MEMBER_OF]->Person" in msg
    assert "Lab" in msg and "ResearchTeam" in msg
    assert exc.value.signature.as_dict() == {
        "from_label": "Person",
        "rel_type": "MEMBER_OF",
        "to_label": "Person",
    }


def test_mentions_entity_expansion() -> None:
    # (Chunk, MENTIONS, Entity) expands to concrete ENTITY_LABELS.
    assert is_allowed_signature("Chunk", "MENTIONS", "Material") is True
    assert "Material" in allowed_targets("Chunk", "MENTIONS")
    # A non-entity target (Section) is not a valid MENTIONS target.
    assert is_allowed_signature("Chunk", "MENTIONS", "Section") is False


def test_allowed_targets_membership_matches_is_allowed() -> None:
    # Invariant: to in allowed_targets(f, r) iff is_allowed_signature(f, r, to).
    for target in allowed_targets("Document", "HAS_SECTION"):
        assert is_allowed_signature("Document", "HAS_SECTION", target) is True
    assert is_allowed_signature("Document", "HAS_SECTION", "Chunk") is False
    assert "Chunk" not in allowed_targets("Document", "HAS_SECTION")


def test_edge_signature_str_and_as_dict() -> None:
    sig = EdgeSignature("Material", "HAS_COMPOSITION", "Composition")
    assert str(sig) == "Material-[:HAS_COMPOSITION]->Composition"
    assert sig.as_dict() == {
        "from_label": "Material",
        "rel_type": "HAS_COMPOSITION",
        "to_label": "Composition",
    }
