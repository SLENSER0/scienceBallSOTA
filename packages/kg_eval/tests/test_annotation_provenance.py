"""Tests for annotation provenance guard (§23.26)."""

from __future__ import annotations

from kg_eval.annotation_provenance import (
    AnnotationProvenance,
    from_meta,
    validate,
)


def _complete_meta(**overrides: object) -> dict[str, object]:
    meta: dict[str, object] = {
        "schema_version": "kg-schema/2.3.0",
        "guidelines_ref": "docs/annotation-guidelines.md#v4",
        "iaa_kappa": 0.8,
        "double_annotated_fraction": 0.3,
    }
    meta.update(overrides)
    return meta


def test_complete_valid_meta_passes() -> None:
    ok, reasons = validate(_complete_meta())
    assert ok is True
    assert reasons == ()


def test_low_kappa_fails() -> None:
    ok, reasons = validate(_complete_meta(iaa_kappa=0.5))
    assert ok is False
    assert "iaa_kappa" in reasons


def test_low_double_annotation_fails() -> None:
    ok, reasons = validate(_complete_meta(double_annotated_fraction=0.1))
    assert ok is False
    assert "double_annotation" in reasons


def test_missing_schema_version_fails() -> None:
    meta = _complete_meta()
    del meta["schema_version"]
    ok, reasons = validate(meta)
    assert ok is False
    assert "schema_version" in reasons


def test_empty_schema_version_fails() -> None:
    ok, reasons = validate(_complete_meta(schema_version=""))
    assert ok is False
    assert "schema_version" in reasons


def test_missing_guidelines_fails() -> None:
    meta = _complete_meta()
    del meta["guidelines_ref"]
    ok, reasons = validate(meta)
    assert ok is False
    assert "guidelines" in reasons


def test_kappa_exactly_at_min_passes() -> None:
    # inclusive lower bound: 0.6 with min 0.6 must pass.
    ok, reasons = validate(_complete_meta(iaa_kappa=0.6), min_kappa=0.6)
    assert ok is True
    assert "iaa_kappa" not in reasons


def test_double_exactly_at_min_passes() -> None:
    ok, _reasons = validate(_complete_meta(double_annotated_fraction=0.2), min_double=0.2)
    assert ok is True


def test_reasons_sorted_deterministically() -> None:
    # Everything wrong at once — reasons must come back sorted.
    ok, reasons = validate(
        {
            "schema_version": "",
            "guidelines_ref": "",
            "iaa_kappa": 0.0,
            "double_annotated_fraction": 0.0,
        }
    )
    assert ok is False
    assert reasons == ("double_annotation", "guidelines", "iaa_kappa", "schema_version")
    assert list(reasons) == sorted(reasons)


def test_custom_thresholds() -> None:
    # A stricter kappa floor turns an otherwise-fine set red.
    ok, reasons = validate(_complete_meta(iaa_kappa=0.7), min_kappa=0.75)
    assert ok is False
    assert "iaa_kappa" in reasons


def test_from_meta_round_trip() -> None:
    meta = _complete_meta()
    prov = from_meta(meta)
    assert isinstance(prov, AnnotationProvenance)
    assert prov.schema_version == "kg-schema/2.3.0"
    assert prov.guidelines_ref == "docs/annotation-guidelines.md#v4"
    assert prov.iaa_kappa == 0.8
    assert prov.double_annotated_fraction == 0.3


def test_as_dict_round_trips_four_fields() -> None:
    prov = AnnotationProvenance(
        schema_version="s1",
        guidelines_ref="g1",
        iaa_kappa=0.9,
        double_annotated_fraction=0.4,
    )
    d = prov.as_dict()
    assert set(d) == {
        "schema_version",
        "guidelines_ref",
        "iaa_kappa",
        "double_annotated_fraction",
    }
    assert AnnotationProvenance(**d) == prov  # type: ignore[arg-type]


def test_frozen_dataclass_is_immutable() -> None:
    prov = from_meta(_complete_meta())
    try:
        prov.iaa_kappa = 0.1  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("AnnotationProvenance must be frozen")
