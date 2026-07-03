"""Tests for public config / feature-flag projection (§14.15).

Проверяем, что наружу уходят только allowlist-флаги (bool), без секретов,
и что ``build_config`` собирает корректный ответ ``GET /config``.
"""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.public_config import (
    PUBLIC_FLAG_ALLOWLIST,
    PublicConfig,
    build_config,
    project_public_flags,
)


def test_allowlist_contents() -> None:
    """Allowlist holds exactly the four client-safe flags."""
    assert (
        frozenset(
            {
                "enable_graphql_proxy",
                "enable_graphrag",
                "enable_uploads",
                "enable_curation",
            }
        )
        == PUBLIC_FLAG_ALLOWLIST
    )


def test_project_keeps_only_allowlisted_and_coerces() -> None:
    """Non-allowlisted secrets dropped; truthy flag coerced to ``True``."""
    result = project_public_flags({"enable_graphql_proxy": 1, "jwt_secret": "x"})
    assert result == {"enable_graphql_proxy": True}
    assert "jwt_secret" not in result


def test_project_empty_mapping() -> None:
    """Empty input yields empty output — nothing injected."""
    assert project_public_flags({}) == {}


def test_project_never_injects_absent_allowlisted_key() -> None:
    """Absent allowlisted key is never added to the projection."""
    assert "enable_graphrag" not in project_public_flags({})


def test_project_values_are_all_bool() -> None:
    """Every projected value is a genuine ``bool`` after coercion."""
    result = project_public_flags(
        {
            "enable_graphql_proxy": 1,
            "enable_graphrag": 0,
            "enable_uploads": "yes",
            "enable_curation": "",
        }
    )
    assert result == {
        "enable_graphql_proxy": True,
        "enable_graphrag": False,
        "enable_uploads": True,
        "enable_curation": False,
    }
    assert all(isinstance(v, bool) for v in result.values())


def test_project_falsy_allowlisted_kept_as_false() -> None:
    """A present-but-falsy allowlisted flag stays (as ``False``), not dropped."""
    result = project_public_flags({"enable_uploads": 0})
    assert result == {"enable_uploads": False}
    assert "enable_uploads" in result


def test_custom_allowlist_overrides_default() -> None:
    """A caller-supplied allowlist replaces the default set."""
    result = project_public_flags(
        {"enable_uploads": True, "enable_curation": True},
        allowlist=frozenset({"enable_uploads"}),
    )
    assert result == {"enable_uploads": True}


def test_build_config_projects_and_stamps_version_build() -> None:
    """``build_config`` projects flags and records version/build."""
    cfg = build_config({"enable_uploads": True}, "1.0", "abc")
    assert isinstance(cfg, PublicConfig)
    as_dict = cfg.as_dict()
    assert as_dict["version"] == "1.0"
    assert as_dict["build"] == "abc"
    assert as_dict["flags"] == {"enable_uploads": True}


def test_build_config_drops_secrets() -> None:
    """Secrets in the raw flag map never reach the built config."""
    cfg = build_config({"enable_uploads": True, "jwt_secret": "s3cr3t"}, "2.1", "deadbeef")
    assert "jwt_secret" not in cfg.flags
    assert cfg.flags == {"enable_uploads": True}


def test_as_dict_shape_and_flag_bools() -> None:
    """``as_dict`` exposes exactly ``{flags, version, build}`` with bool flags."""
    cfg = build_config({"enable_graphql_proxy": 1, "enable_graphrag": 0}, "3.0", "sha")
    as_dict = cfg.as_dict()
    assert set(as_dict.keys()) == {"flags", "version", "build"}
    assert all(isinstance(v, bool) for v in as_dict["flags"].values())


def test_as_dict_flags_is_copy() -> None:
    """``as_dict`` returns a fresh flags dict — mutation is isolated."""
    cfg = build_config({"enable_uploads": True}, "1.0", "abc")
    first = cfg.as_dict()
    first["flags"]["enable_uploads"] = False
    assert cfg.flags["enable_uploads"] is True


def test_public_config_is_frozen() -> None:
    """The DTO is immutable — attribute assignment raises."""
    cfg = build_config({}, "1.0", "abc")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.version = "9.9"  # type: ignore[misc]
