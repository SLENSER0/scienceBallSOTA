"""Hand-checked tests for the §11.2 GraphRAG settings validator.

Каждое ожидаемое значение задано конкретно по §11.2 (модель эмбеддингов, размер
чанка/перекрытие, параметры кластеризации графа).
"""

from __future__ import annotations

import dataclasses

import pytest

from kg_retrievers.graphrag_settings_validator import (
    REQUIRED_KEYS,
    SettingsReport,
    validate_settings,
)

EMB = "BAAI/bge-small-en-v1.5"
SIZE = 1200


def _valid_settings() -> dict:
    """A fully valid §11.2 settings mapping (all required sections present)."""
    return {
        "llm": {"model": "qwen2.5"},
        "embeddings": {"model": EMB},
        "chunks": {"size": SIZE, "overlap": 100},
        "community_reports": {"max_length": 2000},
        "cluster_graph": {"max_cluster_size": 10},
    }


def test_required_keys_are_exact() -> None:
    """REQUIRED_KEYS is the spec §11.2 five-section tuple, in order."""
    assert REQUIRED_KEYS == (
        "llm",
        "embeddings",
        "chunks",
        "community_reports",
        "cluster_graph",
    )


def test_valid_settings_ok_true_echoes_model() -> None:
    """Valid dict → ok True, no errors, embedding_model echoed, no warnings."""
    rep = validate_settings(
        _valid_settings(), expected_embedding_model=EMB, expected_chunk_size=SIZE
    )
    assert rep.ok is True
    assert rep.errors == []
    assert rep.warnings == []
    assert rep.embedding_model == EMB
    assert rep.chunk_size == SIZE
    assert rep.chunk_overlap == 100


def test_embedding_model_mismatch_ok_false() -> None:
    """Wrong embeddings.model → ok False with the mismatch error present."""
    s = _valid_settings()
    s["embeddings"]["model"] = "other/model"
    rep = validate_settings(s, expected_embedding_model=EMB, expected_chunk_size=SIZE)
    assert rep.ok is False
    assert any("embedding model mismatch" in e for e in rep.errors)
    assert rep.embedding_model == "other/model"


def test_missing_community_reports_ok_false() -> None:
    """Dropping 'community_reports' → ok False with a missing-key error."""
    s = _valid_settings()
    del s["community_reports"]
    rep = validate_settings(s, expected_embedding_model=EMB, expected_chunk_size=SIZE)
    assert rep.ok is False
    assert any("community_reports" in e for e in rep.errors)


def test_overlap_ge_size_ok_false() -> None:
    """overlap >= size → ok False with the overlap error."""
    s = _valid_settings()
    s["chunks"] = {"size": 500, "overlap": 500}
    rep = validate_settings(s, expected_embedding_model=EMB, expected_chunk_size=500)
    assert rep.ok is False
    assert any("chunk overlap >= size" in e for e in rep.errors)


def test_chunk_size_mismatch_is_warning_only() -> None:
    """size != expected → ok True with exactly one warning, no errors."""
    s = _valid_settings()
    s["chunks"] = {"size": 800, "overlap": 50}
    rep = validate_settings(s, expected_embedding_model=EMB, expected_chunk_size=SIZE)
    assert rep.ok is True
    assert rep.errors == []
    assert len(rep.warnings) == 1
    assert "differs from expected" in rep.warnings[0]
    assert rep.chunk_size == 800


def test_max_cluster_size_zero_ok_false() -> None:
    """cluster_graph.max_cluster_size == 0 → ok False with the size error."""
    s = _valid_settings()
    s["cluster_graph"] = {"max_cluster_size": 0}
    rep = validate_settings(s, expected_embedding_model=EMB, expected_chunk_size=SIZE)
    assert rep.ok is False
    assert any("max_cluster_size" in e for e in rep.errors)


def test_as_dict_warnings_is_list() -> None:
    """as_dict()['warnings'] is a list (and a fresh copy, not the instance list)."""
    rep = validate_settings(
        _valid_settings(), expected_embedding_model=EMB, expected_chunk_size=SIZE
    )
    d = rep.as_dict()
    assert isinstance(d["warnings"], list)
    assert isinstance(d["errors"], list)
    assert d["ok"] is True
    assert d["embedding_model"] == EMB


def test_absent_embeddings_model_no_crash_just_error() -> None:
    """embeddings section without 'model' → no crash, mismatch error, ok False."""
    s = _valid_settings()
    s["embeddings"] = {}
    rep = validate_settings(s, expected_embedding_model=EMB, expected_chunk_size=SIZE)
    assert rep.ok is False
    assert rep.embedding_model == ""
    assert any("embedding model mismatch" in e for e in rep.errors)


def test_report_is_frozen() -> None:
    """SettingsReport is a frozen dataclass (attribute assignment raises)."""
    rep = SettingsReport(ok=True, embedding_model=EMB, chunk_size=SIZE, chunk_overlap=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        rep.ok = False  # type: ignore[misc]
