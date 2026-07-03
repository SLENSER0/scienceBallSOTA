"""Tests for entity badge/chip descriptors (§17.5). / Тесты бейджей сущностей."""

from __future__ import annotations

from kg_retrievers.entity_badge_descriptor import Badge, BadgeSet, build_badges


def _node(**over: object) -> dict:
    """A base entity node dict with overridable fields. / Базовый узел."""
    base = {
        "type": "Material",
        "confidence": 0.9,
        "verified": True,
        "evidenceCount": 4,
        "missingFields": [],
    }
    base.update(over)
    return base


def test_confidence_high() -> None:
    assert build_badges(_node(confidence=0.9)).confidence_badge.tone == "high"


def test_confidence_medium() -> None:
    assert build_badges(_node(confidence=0.6)).confidence_badge.tone == "medium"


def test_confidence_low() -> None:
    assert build_badges(_node(confidence=0.2)).confidence_badge.tone == "low"


def test_confidence_boundary_high() -> None:
    # Exactly 0.8 is high (inclusive lower bound). / Граница 0.8 включительно.
    assert build_badges(_node(confidence=0.8)).confidence_badge.tone == "high"


def test_confidence_boundary_medium() -> None:
    # Exactly 0.5 is medium (inclusive lower bound). / Граница 0.5 включительно.
    assert build_badges(_node(confidence=0.5)).confidence_badge.tone == "medium"


def test_verified_false_no_lock() -> None:
    assert build_badges(_node(verified=False)).verified_lock is None


def test_verified_true_lock() -> None:
    lock = build_badges(_node(verified=True)).verified_lock
    assert lock is not None
    assert lock.icon == "lock"
    assert lock.tone == "verified"


def test_missing_warning() -> None:
    warning = build_badges(_node(missingFields=["temperature"])).missing_warning
    assert warning is not None
    assert warning.label == "1"
    assert warning.tone == "warning"


def test_missing_warning_absent_when_complete() -> None:
    assert build_badges(_node(missingFields=[])).missing_warning is None


def test_missing_warning_count_two() -> None:
    warning = build_badges(_node(missingFields=["temperature", "pressure"])).missing_warning
    assert warning is not None
    assert warning.label == "2"


def test_type_chip_label() -> None:
    assert build_badges(_node(type="Material")).type_chip.label == "Material"


def test_evidence_badge_label() -> None:
    assert build_badges(_node(evidenceCount=4)).evidence_badge.label == "4"


def test_as_dict_verified_lock_none_when_unverified() -> None:
    assert build_badges(_node(verified=False)).as_dict()["verifiedLock"] is None


def test_as_dict_shape_when_verified() -> None:
    d = build_badges(_node()).as_dict()
    assert d["typeChip"] == {"label": "Material", "tone": "type", "icon": "tag"}
    assert d["confidenceBadge"]["tone"] == "high"
    assert d["verifiedLock"] == {"label": "Verified", "tone": "verified", "icon": "lock"}
    assert d["evidenceBadge"]["label"] == "4"
    assert d["missingWarning"] is None


def test_badge_as_dict() -> None:
    assert Badge("x", "y", "z").as_dict() == {"label": "x", "tone": "y", "icon": "z"}


def test_badgeset_is_frozen() -> None:
    bs = build_badges(_node())
    assert isinstance(bs, BadgeSet)
    try:
        bs.type_chip = Badge("a", "b", "c")  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("BadgeSet should be frozen")


def test_defaults_when_keys_missing() -> None:
    # Empty node: type '', confidence 0.0 -> low, no lock, evidence '0', no warning.
    bs = build_badges({})
    assert bs.type_chip.label == ""
    assert bs.confidence_badge.tone == "low"
    assert bs.verified_lock is None
    assert bs.evidence_badge.label == "0"
    assert bs.missing_warning is None
