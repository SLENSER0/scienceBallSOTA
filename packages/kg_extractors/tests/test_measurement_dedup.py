"""Measurement de-duplication tests (§6.18).

Hand-checked expectations: identity is ``(property, value, unit, subject)``, the
survivor keeps the maximum confidence and the union of evidence ids (first-seen
order), and groups preserve first appearance.
"""

from __future__ import annotations

from kg_extractors.measurement_dedup import MergedMeasurement, dedup_measurements


def _m(
    prop: str,
    value: float | None,
    unit: str | None,
    subject: str,
    *,
    confidence: float,
    evidence_ids: list[str],
) -> dict[str, object]:
    """Build one raw measurement mapping for the de-dup input."""
    return {
        "property": prop,
        "value": value,
        "unit": unit,
        "subject": subject,
        "confidence": confidence,
        "evidence_ids": evidence_ids,
    }


def test_identical_measurements_merge_keeping_max_confidence() -> None:
    """Two copies of one fact collapse to one, keeping the higher confidence."""
    items = [
        _m("yield_strength", 210.0, "MPa", "steel_A", confidence=0.6, evidence_ids=["e1"]),
        _m("yield_strength", 210.0, "MPa", "steel_A", confidence=0.9, evidence_ids=["e2"]),
    ]
    out = dedup_measurements(items)
    assert len(out) == 1
    assert out[0].confidence == 0.9  # max(0.6, 0.9), low copy never drags it down
    assert out[0].property == "yield_strength"
    assert out[0].value == 210.0
    assert out[0].unit == "MPa"
    assert out[0].subject == "steel_A"


def test_evidence_ids_unioned_first_seen_order() -> None:
    """Merged evidence ids are the union across copies, first-seen order, no dups."""
    items = [
        _m("hardness", 55.0, "HRC", "sample_1", confidence=0.5, evidence_ids=["a", "b"]),
        _m("hardness", 55.0, "HRC", "sample_1", confidence=0.7, evidence_ids=["b", "c"]),
        _m("hardness", 55.0, "HRC", "sample_1", confidence=0.4, evidence_ids=["a", "d"]),
    ]
    out = dedup_measurements(items)
    assert len(out) == 1
    assert out[0].evidence_ids == ("a", "b", "c", "d")  # b/a de-duplicated, order kept
    assert out[0].confidence == 0.7


def test_different_values_kept_separate() -> None:
    """210 and 211 are different facts — both survive, in first-seen order."""
    items = [
        _m("yield_strength", 210.0, "MPa", "steel_A", confidence=0.8, evidence_ids=["e1"]),
        _m("yield_strength", 211.0, "MPa", "steel_A", confidence=0.8, evidence_ids=["e2"]),
    ]
    out = dedup_measurements(items)
    assert len(out) == 2
    assert [m.value for m in out] == [210.0, 211.0]
    assert [m.evidence_ids for m in out] == [("e1",), ("e2",)]


def test_unit_different_kept_separate() -> None:
    """Same value in MPa and GPa are distinct facts — kept apart (§9.4)."""
    items = [
        _m("modulus", 200.0, "GPa", "steel_A", confidence=0.8, evidence_ids=["e1"]),
        _m("modulus", 200.0, "MPa", "steel_A", confidence=0.8, evidence_ids=["e2"]),
    ]
    out = dedup_measurements(items)
    assert len(out) == 2
    assert {m.unit for m in out} == {"GPa", "MPa"}


def test_different_subject_kept_separate() -> None:
    """Same measurement about two subjects stays two facts (subject is identity)."""
    items = [
        _m("hardness", 55.0, "HRC", "sample_1", confidence=0.8, evidence_ids=["e1"]),
        _m("hardness", 55.0, "HRC", "sample_2", confidence=0.8, evidence_ids=["e2"]),
    ]
    out = dedup_measurements(items)
    assert len(out) == 2
    assert {m.subject for m in out} == {"sample_1", "sample_2"}


def test_empty_input_yields_empty_list() -> None:
    """No items → empty list (graceful, §6.18)."""
    assert dedup_measurements([]) == []


def test_stable_group_order_preserved() -> None:
    """Output group order follows first appearance, even with later duplicates."""
    items = [
        _m("p_c", 3.0, "u", "s", confidence=0.5, evidence_ids=["e3"]),
        _m("p_a", 1.0, "u", "s", confidence=0.5, evidence_ids=["e1"]),
        _m("p_b", 2.0, "u", "s", confidence=0.5, evidence_ids=["e2"]),
        _m("p_a", 1.0, "u", "s", confidence=0.9, evidence_ids=["e1b"]),  # dup of p_a
    ]
    out = dedup_measurements(items)
    assert [m.property for m in out] == ["p_c", "p_a", "p_b"]  # first-seen, not sorted
    a = next(m for m in out if m.property == "p_a")
    assert a.confidence == 0.9
    assert a.evidence_ids == ("e1", "e1b")


def test_as_dict_projection() -> None:
    """as_dict exposes all fields with evidence_ids as a list (§6.18)."""
    items = [
        _m("density", 7.85, "g/cm3", "steel_A", confidence=0.6, evidence_ids=["e1"]),
        _m("density", 7.85, "g/cm3", "steel_A", confidence=0.95, evidence_ids=["e2"]),
    ]
    out = dedup_measurements(items)
    assert len(out) == 1
    assert out[0].as_dict() == {
        "property": "density",
        "value": 7.85,
        "unit": "g/cm3",
        "subject": "steel_A",
        "confidence": 0.95,
        "evidence_ids": ["e1", "e2"],
    }


def test_none_value_and_unit_merge_and_keyed() -> None:
    """value/unit of None is a valid identity component and merges its copies."""
    items = [
        _m("phase", None, None, "steel_A", confidence=0.3, evidence_ids=["e1"]),
        _m("phase", None, None, "steel_A", confidence=0.8, evidence_ids=["e2"]),
    ]
    out = dedup_measurements(items)
    assert len(out) == 1
    assert out[0].value is None
    assert out[0].unit is None
    assert out[0].confidence == 0.8
    assert out[0].evidence_ids == ("e1", "e2")


def test_merged_measurement_is_frozen() -> None:
    """MergedMeasurement is a frozen dataclass — fields are immutable."""
    m = MergedMeasurement(
        property="p",
        value=1.0,
        unit="u",
        subject="s",
        confidence=0.5,
        evidence_ids=("e1",),
    )
    try:
        m.confidence = 0.9  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - only runs if frozen guard failed
        raise AssertionError("MergedMeasurement must be frozen")
