"""Tests for Text2Cypher schema grounding (§12.10).

Проверяем построение контекста-заземления и валидацию по allowlist меток/связей.
"""

from __future__ import annotations

from kg_retrievers.cypher_schema_ground import (
    SchemaContext,
    build_context,
    validate_against_schema,
)

RELS = ["HAS_PROPERTY", "MEASURED_IN"]


def test_labels_stored_sorted() -> None:
    ctx = build_context(["Material", "Experiment"], RELS)
    assert ctx.labels == ("Experiment", "Material")


def test_duplicate_labels_deduped() -> None:
    ctx = build_context(["Material", "Material", "Experiment"], RELS)
    assert ctx.labels == ("Experiment", "Material")


def test_duplicate_relationships_deduped_and_sorted() -> None:
    ctx = build_context(["Material"], ["MEASURED_IN", "HAS_PROPERTY", "MEASURED_IN"])
    assert ctx.relationships == ("HAS_PROPERTY", "MEASURED_IN")


def test_prompt_contains_every_label_and_relationship() -> None:
    ctx = build_context(["Material", "Experiment"], RELS)
    assert "Allowed labels:" in ctx.prompt
    assert "Allowed relationships:" in ctx.prompt
    for name in ("Material", "Experiment", "HAS_PROPERTY", "MEASURED_IN"):
        assert name in ctx.prompt


def test_validate_allows_known_label() -> None:
    ctx = build_context(["Material", "Experiment"], RELS)
    assert validate_against_schema({"Material"}, set(), ctx) == []


def test_unknown_label_produces_exactly_one_violation() -> None:
    ctx = build_context(["Material", "Experiment"], RELS)
    violations = validate_against_schema({"Foo"}, set(), ctx)
    assert len(violations) == 1
    assert "Foo" in violations[0]


def test_disallowed_relationship_is_flagged() -> None:
    ctx = build_context(["Material"], ["HAS_PROPERTY"])
    violations = validate_against_schema(set(), {"WROTE"}, ctx)
    assert len(violations) == 1
    assert "WROTE" in violations[0]


def test_mixed_violations_are_sorted() -> None:
    ctx = build_context(["Material"], ["HAS_PROPERTY"])
    violations = validate_against_schema({"Zeta", "Alpha"}, {"BAD_REL"}, ctx)
    assert violations == sorted(violations)
    assert len(violations) == 3


def test_allowed_label_and_rel_together_pass() -> None:
    ctx = build_context(["Material"], ["HAS_PROPERTY"])
    assert validate_against_schema({"Material"}, {"HAS_PROPERTY"}, ctx) == []


def test_properties_appear_in_prompt() -> None:
    ctx = build_context(
        ["Material"],
        ["HAS_PROPERTY"],
        properties={"Material": ["name", "formula"]},
    )
    assert "name" in ctx.prompt
    assert "formula" in ctx.prompt
    assert "Properties of Material:" in ctx.prompt


def test_prompt_is_deterministic() -> None:
    a = build_context(["Material", "Experiment"], RELS)
    b = build_context(["Experiment", "Material"], list(reversed(RELS)))
    assert a.prompt == b.prompt


def test_as_dict_keys() -> None:
    ctx = build_context(["Material"], ["HAS_PROPERTY"])
    d = ctx.as_dict()
    assert set(d) == {"labels", "relationships", "prompt"}


def test_context_is_frozen() -> None:
    ctx = build_context(["Material"], ["HAS_PROPERTY"])
    assert isinstance(ctx, SchemaContext)
    try:
        ctx.labels = ("X",)  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("SchemaContext should be frozen")
