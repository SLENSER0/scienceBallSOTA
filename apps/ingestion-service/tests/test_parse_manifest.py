"""Tests for the §5.5/§5.7 parse manifest builder.

Проверки сборщика манифеста разбора документа.
"""

from __future__ import annotations

import json

from ingestion_service.parse_manifest import ParseManifest, build_manifest


def _sample() -> ParseManifest:
    return build_manifest(
        doc_id="doc-42",
        parser_used="docling",
        page_count=12,
        n_sections=5,
        n_tables=3,
        n_figures=2,
        n_images=7,
        artifact_keys=["b", "a", "a"],
        checksums={"a": "sha256:aa", "b": "sha256:bb"},
        ocr_used=True,
    )


def test_artifacts_deduped_and_sorted() -> None:
    m = build_manifest(
        doc_id="d",
        parser_used="p",
        page_count=1,
        n_sections=0,
        n_tables=0,
        n_figures=0,
        n_images=0,
        artifact_keys=["b", "a", "a"],
    )
    assert m.artifacts == ("a", "b")


def test_ocr_used_defaults_false() -> None:
    m = build_manifest(
        doc_id="d",
        parser_used="p",
        page_count=1,
        n_sections=0,
        n_tables=0,
        n_figures=0,
        n_images=0,
        artifact_keys=[],
    )
    assert m.ocr_used is False


def test_checksums_default_empty_dict_not_none() -> None:
    m = build_manifest(
        doc_id="d",
        parser_used="p",
        page_count=1,
        n_sections=0,
        n_tables=0,
        n_figures=0,
        n_images=0,
        artifact_keys=[],
        checksums=None,
    )
    assert m.checksums == {}
    assert m.checksums is not None


def test_json_round_trip_equals() -> None:
    m = _sample()
    assert ParseManifest.from_json(m.to_json()) == m


def test_as_dict_n_tables_matches_input() -> None:
    m = _sample()
    assert m.as_dict()["n_tables"] == 3


def test_page_count_preserved() -> None:
    m = _sample()
    assert m.page_count == 12
    assert m.as_dict()["page_count"] == 12


def test_artifacts_is_tuple() -> None:
    m = _sample()
    assert isinstance(m.artifacts, tuple)


def test_to_json_is_valid_json_dict_with_doc_id() -> None:
    m = _sample()
    parsed = json.loads(m.to_json())
    assert isinstance(parsed, dict)
    assert parsed["doc_id"] == "doc-42"


def test_frozen_instance_is_immutable() -> None:
    m = _sample()
    try:
        m.doc_id = "other"  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("ParseManifest should be immutable")


def test_ocr_used_true_survives_round_trip() -> None:
    m = _sample()
    assert m.ocr_used is True
    assert ParseManifest.from_json(m.to_json()).ocr_used is True
