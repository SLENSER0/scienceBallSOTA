"""Tests for governance policy-set definitions — тесты политик (§10.11)."""

from __future__ import annotations

import pytest

from kg_common.metadata.governance_policies import (
    DEFAULT_POLICIES,
    GovernancePolicy,
    apply_defaults,
    policy_for,
    validate_tag,
)


def test_default_policies_count() -> None:
    """There are exactly four built-in facet policies — ровно четыре."""
    assert len(DEFAULT_POLICIES) == 4


def test_facets_present() -> None:
    """The four expected facets are covered — покрыты нужные фасеты."""
    facets = {p.facet for p in DEFAULT_POLICIES}
    assert facets == {"access", "quality", "pii", "domain"}


def test_access_is_required() -> None:
    """``access`` is a required facet — access обязателен."""
    assert policy_for("access").required is True


def test_non_access_facets_not_required() -> None:
    """Only ``access`` is required — остальные фасеты не обязательны."""
    for facet in ("quality", "pii", "domain"):
        assert policy_for(facet).required is False


def test_default_in_allowed_values() -> None:
    """Every default is a member of its allow-list — дефолт в списке."""
    for policy in DEFAULT_POLICIES:
        assert policy.default in policy.allowed_values


def test_access_allowed_values() -> None:
    """``access`` allows public/internal/restricted — три значения."""
    assert policy_for("access").allowed_values == (
        "public",
        "internal",
        "restricted",
    )
    assert policy_for("access").default == "internal"


def test_quality_policy() -> None:
    """``quality`` allows verified/pending, default pending — качество."""
    p = policy_for("quality")
    assert p.allowed_values == ("verified", "pending")
    assert p.default == "pending"


def test_pii_and_domain_policies() -> None:
    """``pii`` and ``domain`` defaults — pii и domain."""
    assert policy_for("pii").default == "none"
    assert policy_for("domain").default == "materials"


def test_validate_tag_true() -> None:
    """A value inside the allow-list validates — значение допустимо."""
    assert validate_tag("access", "restricted") is True
    assert validate_tag("quality", "verified") is True


def test_validate_tag_false() -> None:
    """A value outside the allow-list fails — значение недопустимо."""
    assert validate_tag("access", "secret") is False


def test_validate_tag_unknown_facet() -> None:
    """An unknown facet is not valid — неизвестный фасет невалиден."""
    assert validate_tag("nope", "whatever") is False


def test_policy_for_unknown_raises() -> None:
    """An unknown facet raises ``KeyError`` — KeyError для неизвестного."""
    with pytest.raises(KeyError):
        policy_for("nope")


def test_apply_defaults_empty() -> None:
    """Empty input gains the facet defaults — пустой вход получает дефолты."""
    out = apply_defaults({})
    assert out["access"] == "internal"
    assert out["quality"] == "pending"
    assert out["pii"] == "none"
    assert out["domain"] == "materials"


def test_apply_defaults_preserves_existing() -> None:
    """Provided values are preserved — заданные значения сохраняются."""
    out = apply_defaults({"access": "public"})
    assert out["access"] == "public"
    # Other facets still filled from defaults.
    assert out["quality"] == "pending"


def test_apply_defaults_does_not_mutate_input() -> None:
    """The input mapping is not mutated — вход не мутируется."""
    src: dict[str, str] = {}
    apply_defaults(src)
    assert src == {}


def test_as_dict_roundtrip() -> None:
    """``as_dict`` exposes all fields — as_dict отдаёт все поля."""
    policy = GovernancePolicy(
        facet="access",
        allowed_values=("public", "internal", "restricted"),
        required=True,
        default="internal",
    )
    assert policy.as_dict() == {
        "facet": "access",
        "allowed_values": ("public", "internal", "restricted"),
        "required": True,
        "default": "internal",
    }


def test_policy_is_frozen() -> None:
    """``GovernancePolicy`` is immutable — политика неизменяема."""
    policy = policy_for("access")
    with pytest.raises(AttributeError):
        policy.default = "public"  # type: ignore[misc]
