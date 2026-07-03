"""Tests for the §24.12 lab_capability_profile builder.

Тесты для сборщика профиля возможностей лаборатории (§24.12).
"""

from __future__ import annotations

from kg_retrievers.lab_capability_profile import (
    LabCapabilityProfile,
    build_lab_capability_profile,
)


def test_equipment_deduped_and_sorted() -> None:
    """Assertion (1): ['XRD','XRD','ICP'] → ('ICP','XRD')."""
    profile = build_lab_capability_profile("lab1", {"equipment": ["XRD", "XRD", "ICP"]})
    assert profile.equipment == ("ICP", "XRD")


def test_activity_score_with_mixed_experiments() -> None:
    """Assertion (2): 3 experiments, 2 confirmed → count 2, score 2.5."""
    records = {
        "experiments": [
            {"confirmed": True, "year": 2020},
            {"confirmed": True, "year": 2021},
            {"confirmed": False, "year": 2022},
        ]
    }
    profile = build_lab_capability_profile("lab1", records)
    assert profile.n_confirmed_experiments == 2
    assert profile.activity_score == 2.5


def test_activity_score_all_confirmed() -> None:
    """Assertion (3): all confirmed → activity_score == n."""
    records = {
        "experiments": [
            {"confirmed": True, "year": 2020},
            {"confirmed": True, "year": 2021},
            {"confirmed": True, "year": 2022},
            {"confirmed": True, "year": 2023},
        ]
    }
    profile = build_lab_capability_profile("lab1", records)
    assert profile.n_confirmed_experiments == 4
    assert profile.activity_score == float(4)
    assert profile.activity_score == 4.0


def test_missing_materials_key_is_empty_tuple() -> None:
    """Assertion (4): missing 'materials' key → empty tuple."""
    profile = build_lab_capability_profile("lab1", {"equipment": ["XRD"]})
    assert profile.materials == ()


def test_empty_records() -> None:
    """Assertion (5): empty records → 0 confirmed, 0.0 activity."""
    profile = build_lab_capability_profile("lab1", {})
    assert profile.n_confirmed_experiments == 0
    assert profile.activity_score == 0.0
    assert profile.equipment == ()
    assert profile.processes == ()
    assert profile.materials == ()


def test_as_dict_equipment_is_list() -> None:
    """Assertion (6): as_dict()['equipment'] is a list."""
    profile = build_lab_capability_profile("lab1", {"equipment": ["XRD", "ICP"]})
    payload = profile.as_dict()
    assert isinstance(payload["equipment"], list)
    assert payload["equipment"] == ["ICP", "XRD"]


def test_lab_id_preserved() -> None:
    """Assertion (7): lab_id preserved."""
    profile = build_lab_capability_profile("nano-lab-42", {})
    assert profile.lab_id == "nano-lab-42"
    assert profile.as_dict()["lab_id"] == "nano-lab-42"


def test_frozen_dataclass() -> None:
    """The profile is an immutable frozen dataclass instance."""
    profile = build_lab_capability_profile("lab1", {})
    assert isinstance(profile, LabCapabilityProfile)
    try:
        profile.lab_id = "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("LabCapabilityProfile must be frozen")


def test_all_unconfirmed_half_points() -> None:
    """Unconfirmed-only experiments contribute 0.5 each, 0 confirmed."""
    records = {
        "experiments": [
            {"confirmed": False, "year": 2020},
            {"confirmed": False, "year": 2021},
        ]
    }
    profile = build_lab_capability_profile("lab1", records)
    assert profile.n_confirmed_experiments == 0
    assert profile.activity_score == 1.0


def test_processes_and_materials_deduped_sorted() -> None:
    """Process and material inventories are deduped and sorted too."""
    records = {
        "processes": ["anneal", "etch", "anneal"],
        "materials": ["Si", "GaN", "Si"],
    }
    profile = build_lab_capability_profile("lab1", records)
    assert profile.processes == ("anneal", "etch")
    assert profile.materials == ("GaN", "Si")
