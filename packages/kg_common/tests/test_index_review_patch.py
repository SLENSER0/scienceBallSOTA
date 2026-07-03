"""Тесты билдера патчей индекса — index review patch builder tests (§16.6)."""

from __future__ import annotations

import pytest

from kg_common.storage.index_review_patch import IndexPatch, applies_to, build_patch


def test_accept_sets_accepted_and_verified() -> None:
    patch = build_patch("accept", {}, doc_ids=["d1"])
    assert patch.fields == {"review_status": "accepted", "verified": True}
    assert patch.doc_ids == ("d1",)


def test_reject_sets_verified_false() -> None:
    patch = build_patch("reject", {}, doc_ids=["d1"])
    assert patch.fields == {"review_status": "rejected", "verified": False}


def test_correct_includes_confidence_from_target() -> None:
    patch = build_patch("correct", {"confidence": 0.8}, doc_ids=["d1"])
    assert patch.fields == {
        "review_status": "corrected",
        "verified": True,
        "confidence": 0.8,
    }


def test_correct_without_confidence_omits_field() -> None:
    patch = build_patch("correct", {}, doc_ids=["d1"])
    assert patch.fields == {"review_status": "corrected", "verified": True}
    assert "confidence" not in patch.fields


def test_mark_verified_only_sets_verified() -> None:
    patch = build_patch("mark_verified", {}, doc_ids=["d1"])
    assert patch.fields == {"verified": True}


def test_merge_includes_canonical_id_from_target() -> None:
    patch = build_patch("merge", {"canonical_id": "canon-42"}, doc_ids=["d1", "d2"])
    assert patch.fields == {"canonical_id": "canon-42"}
    assert patch.doc_ids == ("d1", "d2")


def test_applies_to_distinguishes_propagating_actions() -> None:
    assert applies_to("alias_add") is False
    assert applies_to("accept") is True
    for action in ("reject", "correct", "mark_verified", "merge"):
        assert applies_to(action) is True


def test_as_dict_returns_lists_and_fields() -> None:
    result = IndexPatch(doc_ids=("d1", "d2")).as_dict()
    assert result["doc_ids"] == ["d1", "d2"]
    assert result["fields"] == {}


def test_as_dict_carries_fields() -> None:
    patch = build_patch("accept", {}, doc_ids=["d1"])
    assert patch.as_dict() == {
        "doc_ids": ["d1"],
        "fields": {"review_status": "accepted", "verified": True},
    }


def test_unknown_action_raises_value_error() -> None:
    with pytest.raises(ValueError, match="non-propagating"):
        build_patch("alias_add", {}, doc_ids=["d1"])
