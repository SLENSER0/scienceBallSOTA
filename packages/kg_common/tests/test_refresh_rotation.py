"""Refresh-token rotation + reuse-detection tests (§19.2 auth).

All timing is driven by explicit ``now`` arguments — deterministic, no real
``time.sleep``. Values are hand-checkable against the frozen spec assertions.
Каждый шаг ротации проверяется вручную.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_common.security.refresh_rotation import (
    RefreshToken,
    RefreshTokenStore,
    RotationResult,
)


def _fresh_store() -> RefreshTokenStore:
    """Build a store with one active root ``r0`` in family ``fam`` at t=0."""
    store = RefreshTokenStore()
    store.issue_root("r0", "fam", 0.0)
    return store


def test_spec_assertion_walkthrough() -> None:
    store = RefreshTokenStore()
    store.issue_root("r0", "fam", 0.0)
    assert store.is_active("r0") is True

    res = store.rotate("r0", "r1", 1.0)
    assert res.reuse_detected is False
    assert store.is_active("r0") is False
    assert store.is_active("r1") is True
    assert res.new_token is not None
    assert res.new_token.parent_id == "r0"

    reuse = store.rotate("r0", "r2", 2.0)  # replay of the already-rotated token
    assert reuse.reuse_detected is True
    assert store.is_active("r1") is False  # whole family revoked
    assert "r1" in reuse.revoked_ids

    ghost = store.rotate("ghost", "rX", 3.0)  # token we never issued
    assert ghost.reuse_detected is True


def test_issue_root_is_active_and_has_no_parent() -> None:
    store = _fresh_store()
    assert store.is_active("r0") is True
    # A never-issued token is not active.
    assert store.is_active("nope") is False


def test_rotate_child_metadata_is_correct() -> None:
    store = _fresh_store()
    res = store.rotate("r0", "r1", 1.0)
    child = res.new_token
    assert isinstance(child, RefreshToken)
    assert child.token_id == "r1"
    assert child.family_id == "fam"
    assert child.issued_at == 1.0
    assert child.parent_id == "r0"
    assert res.revoked_ids == ("r0",)


def test_multi_step_chain_keeps_only_the_tip_active() -> None:
    store = _fresh_store()
    store.rotate("r0", "r1", 1.0)
    store.rotate("r1", "r2", 2.0)
    res = store.rotate("r2", "r3", 3.0)
    assert res.reuse_detected is False
    assert store.is_active("r0") is False
    assert store.is_active("r1") is False
    assert store.is_active("r2") is False
    assert store.is_active("r3") is True
    assert res.new_token is not None
    assert res.new_token.parent_id == "r2"


def test_reuse_revokes_entire_family_including_live_tip() -> None:
    store = _fresh_store()
    store.rotate("r0", "r1", 1.0)
    store.rotate("r1", "r2", 2.0)
    # r2 is the live tip; replay the stale r0 -> everything dies.
    reuse = store.rotate("r0", "rX", 3.0)
    assert reuse.reuse_detected is True
    assert reuse.new_token is None
    assert store.is_active("r2") is False
    assert set(reuse.revoked_ids) == {"r2"}  # only still-active members revoked


def test_reuse_only_revokes_currently_active_members() -> None:
    store = _fresh_store()
    store.rotate("r0", "r1", 1.0)  # r0 now revoked, r1 active
    reuse = store.rotate("r0", "rX", 2.0)
    # r0 was already revoked; only the still-active r1 is newly revoked.
    assert reuse.revoked_ids == ("r1",)


def test_unknown_token_trips_reuse_without_touching_families() -> None:
    store = _fresh_store()
    ghost = store.rotate("ghost", "rX", 3.0)
    assert ghost.reuse_detected is True
    assert ghost.new_token is None
    assert ghost.revoked_ids == ()
    # The legitimate root is untouched by an unrelated ghost replay.
    assert store.is_active("r0") is True


def test_families_are_isolated() -> None:
    store = RefreshTokenStore()
    store.issue_root("a0", "famA", 0.0)
    store.issue_root("b0", "famB", 0.0)
    store.rotate("a0", "a1", 1.0)
    reuse = store.rotate("a0", "aX", 2.0)  # theft in famA
    assert reuse.reuse_detected is True
    assert store.is_active("a1") is False  # famA dead
    assert store.is_active("b0") is True  # famB untouched


def test_second_reuse_after_family_revoked_is_still_reuse() -> None:
    store = _fresh_store()
    store.rotate("r0", "r1", 1.0)
    store.rotate("r0", "rX", 2.0)  # trips reuse, revokes family
    again = store.rotate("r1", "rY", 3.0)  # r1 already revoked
    assert again.reuse_detected is True
    assert again.new_token is None
    assert again.revoked_ids == ()  # nothing left active to revoke


def test_rotation_result_as_dict_round_trips() -> None:
    store = _fresh_store()
    res = store.rotate("r0", "r1", 1.0)
    d = res.as_dict()
    assert d["reuse_detected"] is False
    assert d["revoked_ids"] == ["r0"]
    assert d["new_token"]["token_id"] == "r1"
    assert d["new_token"]["parent_id"] == "r0"

    reuse = store.rotate("r0", "r2", 2.0)
    rd = reuse.as_dict()
    assert rd["reuse_detected"] is True
    assert rd["new_token"] is None
    assert "r1" in rd["revoked_ids"]


def test_refresh_token_as_dict_shape() -> None:
    tok = RefreshToken(token_id="r1", family_id="fam", issued_at=1.5, parent_id="r0")
    assert tok.as_dict() == {
        "token_id": "r1",
        "family_id": "fam",
        "issued_at": 1.5,
        "parent_id": "r0",
    }


def test_value_objects_are_frozen() -> None:
    tok = RefreshToken("r1", "fam", 1.0, None)
    res = RotationResult(new_token=tok, revoked_ids=("r0",), reuse_detected=False)
    with pytest.raises(FrozenInstanceError):
        tok.token_id = "x"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        res.reuse_detected = True  # type: ignore[misc]
