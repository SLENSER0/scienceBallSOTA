"""Root pytest configuration & shared fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def settings():  # type: ignore[no-untyped-def]
    from kg_common.config import Settings

    return Settings(_env_file=None)  # type: ignore[call-arg]


def has_llm_key() -> bool:
    from kg_common.config import Settings

    key = Settings(_env_file=None).llm_api_key.get_secret_value()  # type: ignore[call-arg]
    return bool(key) or bool(os.environ.get("OPENROUTER_API_KEY"))


requires_llm = pytest.mark.skipif(
    not has_llm_key(), reason="needs OPENROUTER_API_KEY (OSS models via OpenRouter)"
)
