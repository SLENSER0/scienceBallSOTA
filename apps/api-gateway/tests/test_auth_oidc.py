"""§19 OIDC (authentik) group→role mapping + inert-by-default behaviour."""

from __future__ import annotations

from api_gateway import auth_oidc
from api_gateway.auth_oidc import (
    claims_to_identity,
    oidc_enabled,
    public_oidc_config,
    role_for_groups,
    verify_oidc_token,
)


def test_disabled_by_default() -> None:
    # No OIDC_ISSUER configured in the test env → SSO inert.
    assert oidc_enabled() is False
    assert verify_oidc_token("anything.at.all") is None
    assert public_oidc_config() == {"enabled": False}


def test_group_maps_to_admin() -> None:
    assert role_for_groups(["science-ball-admins"]) == "admin"


def test_bare_role_group_resolves() -> None:
    assert role_for_groups(["curator"]) == "curator"


def test_highest_privilege_wins() -> None:
    role = role_for_groups(["science-ball-researchers", "science-ball-admins"])
    assert role == "admin"


def test_unknown_group_is_least_privilege() -> None:
    assert role_for_groups(["some-random-group"]) == "external_partner"
    assert role_for_groups([]) == "external_partner"


def test_case_insensitive_groups() -> None:
    assert role_for_groups(["Science-Ball-Curators"]) == "curator"


def test_claims_to_identity() -> None:
    user, role = claims_to_identity(
        {"preferred_username": "alice", "groups": ["science-ball-analysts"]}
    )
    assert user == "alice"
    assert role == "analyst"


def test_claims_string_group_and_sub_fallback() -> None:
    user, role = claims_to_identity({"sub": "u-42", "groups": "science-ball-managers"})
    assert user == "u-42"
    assert role == "project_manager"


def test_public_config_enabled(monkeypatch) -> None:
    class _S:
        oidc_issuer = "https://auth.example/application/o/science-ball/"
        oidc_client_id = "science-ball"
        oidc_audience = "science-ball"

    monkeypatch.setattr(auth_oidc, "get_settings", lambda: _S())
    # Discovery is unreachable in the test env → falls back to the issuer-root path.
    monkeypatch.setattr(
        auth_oidc, "_discovery", lambda _i: (_ for _ in ()).throw(RuntimeError("offline"))
    )
    cfg = public_oidc_config()
    assert cfg["enabled"] is True
    assert cfg["client_id"] == "science-ball"
    assert cfg["authorize_url"].endswith("/authorize/")
