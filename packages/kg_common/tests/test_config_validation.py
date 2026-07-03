"""§2.2 server-profile required-var validation (Settings.validate_required)."""

from __future__ import annotations

import pytest

from kg_common.config import Settings


def _settings(**overrides: object) -> Settings:
    # Fields use env aliases (RUNTIME_PROFILE …); override by attribute so tests
    # don't depend on alias-vs-name construction semantics.
    s = Settings()
    for key, value in overrides.items():
        setattr(s, key, value)
    return s


def test_embedded_profile_skips_validation() -> None:
    _settings(runtime_profile="embedded").validate_required()  # no raise


def test_server_profile_ok_with_defaults() -> None:
    _settings(runtime_profile="server", app_env="local").validate_required()


def test_server_profile_missing_url_raises() -> None:
    s = _settings(runtime_profile="server", neo4j_uri="")
    with pytest.raises(RuntimeError, match="NEO4J_URI"):
        s.validate_required()


def test_server_non_local_placeholder_password_raises() -> None:
    s = _settings(runtime_profile="server", app_env="prod")
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
        s.validate_required()
