"""Tests for pipeline stage handoff contracts (§6.16 / §23.2)."""

from __future__ import annotations

from typing import Any

from kg_schema.handoff import (
    HANDOFF_MODELS,
    ChunkHandoff,
    ERHandoff,
    ExtractionHandoff,
    NormalizationHandoff,
    UpsertHandoff,
    validate_handoff,
)


def _good_chunk() -> dict[str, Any]:
    return {
        "chunk_id": "chunk:c1",
        "doc_id": "doc:d1",
        "text": "Твёрдость 450 HV после закалки.",
        "section_path": "Results/Hardness",
        "chunk_type": "text",
        "tokens": 12,
    }


def _good_extraction() -> dict[str, Any]:
    return {
        "chunk_id": "chunk:c1",
        "entities": [{"text": "steel", "entity_type": "Material"}],
        "measurements": [{"value": 450.0, "unit": "HV"}],
        "needs_custom_normalization": True,
    }


def _good_normalization() -> dict[str, Any]:
    return {
        "measurements": [{"value_normalized": 450.0, "normalized_unit": "HV"}],
        "flagged": [{"value": 55.0, "unit": "HRC", "reason": "no pint conversion"}],
    }


def _good_er() -> dict[str, Any]:
    return {
        "mentions": [{"text": "304 stainless"}, {"text": "SS304"}],
        "entity_type": "Material",
    }


def _good_upsert() -> dict[str, Any]:
    return {
        "node_id": "measurement:m1",
        "label": "Measurement",
        "props": {"value": 450.0, "unit": "HV"},
        "provenance": {
            "extractor_run_id": "run:1",
            "schema_version": "1.4.0",
            "created_at": "2026-07-03T00:00:00Z",
        },
    }


# --- each model validates a good payload -------------------------------------


def test_chunk_handoff_valid() -> None:
    m = ChunkHandoff.model_validate(_good_chunk())
    assert m.chunk_id == "chunk:c1"
    assert m.doc_id == "doc:d1"
    assert m.tokens == 12


def test_extraction_handoff_valid() -> None:
    m = ExtractionHandoff.model_validate(_good_extraction())
    assert m.chunk_id == "chunk:c1"
    assert m.needs_custom_normalization is True
    assert m.measurements[0]["unit"] == "HV"


def test_normalization_handoff_valid() -> None:
    m = NormalizationHandoff.model_validate(_good_normalization())
    assert len(m.measurements) == 1
    assert m.flagged[0]["unit"] == "HRC"


def test_er_handoff_valid() -> None:
    m = ERHandoff.model_validate(_good_er())
    assert m.entity_type == "Material"
    assert len(m.mentions) == 2


def test_upsert_handoff_valid() -> None:
    m = UpsertHandoff.model_validate(_good_upsert())
    assert m.node_id == "measurement:m1"
    assert m.label == "Measurement"
    assert m.provenance["schema_version"] == "1.4.0"


# --- camelCase alias round-trips ---------------------------------------------


def test_camel_alias_round_trips() -> None:
    # Parse camelCase (needsCustomNormalization / chunkId) as the frontend would send.
    m = ExtractionHandoff.model_validate({"chunkId": "chunk:c1", "needsCustomNormalization": True})
    assert m.chunk_id == "chunk:c1"
    assert m.needs_custom_normalization is True
    # Dump back to camelCase: aliases survive the round-trip.
    dumped = m.model_dump(by_alias=True)
    assert dumped["needsCustomNormalization"] is True
    assert dumped["chunkId"] == "chunk:c1"
    assert "needs_custom_normalization" not in dumped


def test_snake_case_also_accepted() -> None:
    # populate_by_name=True (inherited from CamelModel) accepts field names too.
    payload = {"chunk_id": "chunk:c1", "needs_custom_normalization": True}
    m = ExtractionHandoff.model_validate(payload)
    assert m.chunk_id == "chunk:c1"
    assert m.needs_custom_normalization is True


# --- validate_handoff dispatch by stage --------------------------------------


def test_validate_handoff_dispatch_all_stages() -> None:
    cases = {
        "chunk": _good_chunk(),
        "extraction": _good_extraction(),
        "normalization": _good_normalization(),
        "er": _good_er(),
        "upsert": _good_upsert(),
    }
    for stage, payload in cases.items():
        result = validate_handoff(stage, payload)
        assert result == {"valid": True, "errors": []}, f"{stage} should validate"


def test_registry_maps_stage_to_model() -> None:
    assert HANDOFF_MODELS["chunk"] is ChunkHandoff
    assert HANDOFF_MODELS["extraction"] is ExtractionHandoff
    assert HANDOFF_MODELS["normalization"] is NormalizationHandoff
    assert HANDOFF_MODELS["er"] is ERHandoff
    assert HANDOFF_MODELS["upsert"] is UpsertHandoff
    assert set(HANDOFF_MODELS) == {"chunk", "extraction", "normalization", "er", "upsert"}


# --- unknown stage -> error --------------------------------------------------


def test_unknown_stage_is_error() -> None:
    result = validate_handoff("does_not_exist", {})
    assert result["valid"] is False
    assert result["errors"]
    assert "unknown stage" in result["errors"][0]


# --- missing required field -> invalid ---------------------------------------


def test_missing_required_field_invalid() -> None:
    # UpsertHandoff requires node_id; omit it -> invalid with the field named.
    result = validate_handoff("upsert", {"label": "Measurement"})
    assert result["valid"] is False
    assert any("nodeId" in e or "node_id" in e for e in result["errors"])


def test_missing_required_field_direct_er() -> None:
    # ERHandoff requires entity_type.
    result = validate_handoff("er", {"mentions": []})
    assert result["valid"] is False
    assert any("entityType" in e or "entity_type" in e for e in result["errors"])


# --- extra fields ignored per model config -----------------------------------


def test_extra_fields_ignored() -> None:
    # CamelModel base sets extra="ignore": unknown keys are dropped, not rejected.
    payload = {**_good_chunk(), "bogusField": "drop-me", "another": 1}
    m = ChunkHandoff.model_validate(payload)
    dumped = m.model_dump()
    assert "bogusField" not in dumped
    assert "another" not in dumped
    # Still a valid handoff despite the extras.
    assert validate_handoff("chunk", payload) == {"valid": True, "errors": []}


def test_all_models_ignore_extra() -> None:
    for model in HANDOFF_MODELS.values():
        assert model.model_config.get("extra") == "ignore"
