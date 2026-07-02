"""Settings load from environment / .env (§1.9)."""

from __future__ import annotations

from kg_common.config import Settings


def test_settings_defaults_valid() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.runtime_profile in {"embedded", "server"}
    assert s.embedding_dim == 384
    # OSS-only default models (Apache-2.0 / MIT)
    assert "qwen" in s.llm_model_extract or "mistral" in s.llm_model_extract
    assert s.llm_api_base.startswith("https://")


def test_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("LLM_MODEL_EXTRACT", "mistralai/mistral-nemo")
    monkeypatch.setenv("EMBEDDING_DIM", "512")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm_model_extract == "mistralai/mistral-nemo"
    assert s.embedding_dim == 512


def test_dto_camel_aliases() -> None:
    from kg_common.dto import GraphNode

    n = GraphNode(id="material:ni", label="Nickel", type="Material", evidence_count=3)
    dumped = n.model_dump(by_alias=True)
    assert dumped["evidenceCount"] == 3  # camelCase for the frontend
