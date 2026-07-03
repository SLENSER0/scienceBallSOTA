"""Tests for the versioned prompt registry (§13.1 / §13.23).

Hand-checkable: fixed placeholder substitution, exact registry key set, and a
manually-recomputed sha256 fingerprint over the sorted ``name:version`` lines.
"""

from __future__ import annotations

import hashlib
import re

import pytest
from agent_service.prompt_registry import (
    REGISTRY,
    PromptTemplate,
    active_versions,
    get_prompt,
    versions_fingerprint,
)

_EXPECTED_NAMES = {
    "intent_classifier",
    "query_planner",
    "verifier",
    "answer_synthesizer",
}


def test_verifier_version_non_empty() -> None:
    """(1) get_prompt('verifier').version is non-empty."""
    assert get_prompt("verifier").version


def test_render_substitutes() -> None:
    """(2) render does str.format substitution."""
    tpl = PromptTemplate("t", "v1", "Q: {q}")
    assert tpl.render(q="Al") == "Q: Al"


def test_get_prompt_unknown_raises_keyerror() -> None:
    """(3) unknown name raises KeyError."""
    with pytest.raises(KeyError):
        get_prompt("nope")


def test_active_versions_exact_keys() -> None:
    """(4) active_versions() has exactly the four expected keys."""
    versions = active_versions()
    assert set(versions) == _EXPECTED_NAMES
    assert all(v for v in versions.values())


def test_fingerprint_is_64_hex_and_stable() -> None:
    """(5) fingerprint is 64 hex chars and stable across two calls."""
    fp1 = versions_fingerprint()
    fp2 = versions_fingerprint()
    assert fp1 == fp2
    assert re.fullmatch(r"[0-9a-f]{64}", fp1)


def test_fingerprint_manual_recompute() -> None:
    """(5b) fingerprint matches a hand-recomputed sha256 over sorted lines."""
    lines = sorted(f"{name}:{tpl.version}" for name, tpl in REGISTRY.items())
    expected = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    assert versions_fingerprint() == expected


def test_fingerprint_order_independent() -> None:
    """(6) identical name/version pairs → same fingerprint, any insert order."""
    a = PromptTemplate("a", "v1", "A {x}")
    b = PromptTemplate("b", "v2", "B {y}")
    reg_ab = {"a": a, "b": b}
    reg_ba = {"b": b, "a": a}
    assert versions_fingerprint(reg_ab) == versions_fingerprint(reg_ba)


def test_as_dict_exposes_fields() -> None:
    """(7) as_dict exposes name/version/template."""
    tpl = PromptTemplate("t", "v1", "body {slot}")
    assert tpl.as_dict() == {"name": "t", "version": "v1", "template": "body {slot}"}


def test_builtin_bodies_have_placeholders() -> None:
    """Every builtin template body has at least one {placeholder} slot."""
    for tpl in REGISTRY.values():
        assert re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", tpl.template)
