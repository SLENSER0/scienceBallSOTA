"""Tests for §17.14 'Discuss this gap' seed chat context. / Тесты контекста чата."""

from __future__ import annotations

from kg_retrievers.gap_chat_context import (
    SEED_TEMPLATES,
    GapChatContext,
    build_gap_chat_context,
)


def test_missing_property_value_mentions_property_and_entity() -> None:
    gap = {
        "id": "gap-1",
        "gapType": "missing_property_value",
        "entityId": "ent-42",
        "entity": "PEM electrolyzer",
        "property": "efficiency",
    }
    ctx = build_gap_chat_context(gap)
    assert "efficiency" in ctx.seed_question
    assert "PEM electrolyzer" in ctx.seed_question


def test_gap_type_passed_through_verbatim() -> None:
    ctx = build_gap_chat_context({"gapType": "missing_property_value", "entity": "X"})
    assert ctx.gap_type == "missing_property_value"


def test_low_coverage_material_mentions_coverage() -> None:
    gap = {"gapType": "low_coverage_material", "material": "Nafion 117", "id": "g9"}
    ctx = build_gap_chat_context(gap)
    assert "coverage" in ctx.seed_question.lower()
    assert "Nafion 117" in ctx.seed_question


def test_unknown_type_falls_back_to_generic() -> None:
    gap = {"gapType": "totally_unknown_type", "description": "some subject", "id": "g0"}
    ctx = build_gap_chat_context(gap)
    assert "data gaps" in ctx.seed_question.lower()
    assert "some subject" in ctx.seed_question
    assert ctx.gap_type == "totally_unknown_type"


def test_entity_id_mirrors_gap_field() -> None:
    ctx = build_gap_chat_context({"gapType": "orphan_entity", "entityId": "ent-7"})
    assert ctx.entity_id == "ent-7"

    ctx_none = build_gap_chat_context({"gapType": "orphan_entity"})
    assert ctx_none.entity_id is None


def test_filters_include_property_when_present_else_omitted() -> None:
    with_prop = build_gap_chat_context(
        {"gapType": "missing_property_value", "entity": "E", "property": "bandgap"}
    )
    assert with_prop.filters["property"] == "bandgap"

    without_prop = build_gap_chat_context({"gapType": "orphan_entity", "entity": "E"})
    assert "property" not in without_prop.filters


def test_filters_include_material_when_present() -> None:
    ctx = build_gap_chat_context({"gapType": "low_coverage_material", "material": "Pt/C"})
    assert ctx.filters["material"] == "Pt/C"


def test_gap_ids_is_tuple_containing_id() -> None:
    ctx = build_gap_chat_context({"gapType": "orphan_entity", "id": "gap-123"})
    assert isinstance(ctx.gap_ids, tuple)
    assert ctx.gap_ids == ("gap-123",)

    empty = build_gap_chat_context({"gapType": "orphan_entity"})
    assert empty.gap_ids == ()


def test_as_dict_has_expected_keys() -> None:
    ctx = build_gap_chat_context(
        {
            "id": "g1",
            "gapType": "missing_property_value",
            "entityId": "e1",
            "entity": "E",
            "property": "p",
        }
    )
    d = ctx.as_dict()
    assert set(d) == {"seedQuestion", "gapType", "entityId", "filters", "gapIds"}
    assert d["seedQuestion"] == ctx.seed_question
    assert d["gapType"] == "missing_property_value"
    assert d["entityId"] == "e1"
    assert d["filters"]["property"] == "p"
    assert d["gapIds"] == ["g1"]


def test_frozen_dataclass_is_immutable() -> None:
    ctx = build_gap_chat_context({"gapType": "orphan_entity", "id": "g1"})
    assert isinstance(ctx, GapChatContext)
    try:
        ctx.seed_question = "mutated"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must raise
        raise AssertionError("GapChatContext should be frozen")


def test_seed_templates_cover_known_gap_types() -> None:
    # A representative sample of §11.1 gap types must have dedicated templates.
    for gtype in ("missing_property_value", "low_coverage_material", "orphan_entity"):
        assert gtype in SEED_TEMPLATES


def test_gap_type_from_snake_case_alias() -> None:
    ctx = build_gap_chat_context({"gap_type": "low_coverage_material", "material": "M"})
    assert ctx.gap_type == "low_coverage_material"
    assert "coverage" in ctx.seed_question.lower()
