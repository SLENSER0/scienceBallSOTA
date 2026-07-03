"""Tests for the Content-Security-Policy directive builder (§19.7).

Hand-checkable cases over small explicit policies covering the self-only
baseline, alphabetical joining, nonce injection, ``upgrade-insecure-requests``,
``report-uri``, empty-directive omission, immutability of :func:`with_nonce`,
and :meth:`CspPolicy.as_dict` round-tripping.
"""

from __future__ import annotations

from kg_common.security.csp_builder import (
    CspPolicy,
    build_csp,
    default_policy,
    with_nonce,
)


def test_default_policy_has_self_default_src() -> None:
    """(1) The baseline policy declares ``default-src 'self'``."""
    assert "default-src 'self'" in build_csp(default_policy())


def test_directives_joined_sorted_by_name() -> None:
    """(2) Multiple directives are joined by '; ' in alphabetical order."""
    policy = CspPolicy(
        directives={
            "script-src": ("'self'",),
            "default-src": ("'self'",),
            "img-src": ("'self'", "data:"),
        }
    )
    result = build_csp(policy)
    assert result == "default-src 'self'; img-src 'self' data:; script-src 'self'"


def test_nonce_injected_into_script_src() -> None:
    """(3) A nonce is injected as ``'nonce-abc'`` into the script-src directive."""
    policy = CspPolicy(directives={"script-src": ("'self'",)})
    result = build_csp(policy, nonce="abc")
    assert "script-src 'self' 'nonce-abc'" in result


def test_upgrade_insecure_appended() -> None:
    """(4) ``upgrade_insecure=True`` appends 'upgrade-insecure-requests'."""
    policy = CspPolicy(directives={"default-src": ("'self'",)}, upgrade_insecure=True)
    result = build_csp(policy)
    assert result == "default-src 'self'; upgrade-insecure-requests"


def test_report_uri_appended() -> None:
    """(5) ``report_uri='/csp'`` appends 'report-uri /csp'."""
    policy = CspPolicy(directives={"default-src": ("'self'",)}, report_uri="/csp")
    result = build_csp(policy)
    assert result == "default-src 'self'; report-uri /csp"


def test_empty_directive_omitted() -> None:
    """(6) A directive mapped to ``()`` is omitted from output."""
    policy = CspPolicy(directives={"default-src": ("'self'",), "frame-src": ()})
    result = build_csp(policy)
    assert result == "default-src 'self'"
    assert "frame-src" not in result


def test_with_nonce_leaves_original_unchanged() -> None:
    """(7) ``with_nonce`` returns a new policy without mutating the original."""
    original = CspPolicy(directives={"script-src": ("'self'",), "style-src": ("'self'",)})
    derived = with_nonce(original, "xyz")
    assert derived is not original
    assert original.directives["script-src"] == ("'self'",)
    assert derived.directives["script-src"] == ("'self'", "'nonce-xyz'")
    assert derived.directives["style-src"] == ("'self'", "'nonce-xyz'")


def test_as_dict_round_trips_report_uri_and_upgrade() -> None:
    """(8) ``as_dict`` round-trips report_uri and upgrade_insecure."""
    policy = CspPolicy(
        directives={"default-src": ("'self'",)},
        report_uri="/csp",
        upgrade_insecure=True,
    )
    snapshot = policy.as_dict()
    assert snapshot["report_uri"] == "/csp"
    assert snapshot["upgrade_insecure"] is True
    assert snapshot["directives"] == {"default-src": ("'self'",)}
