"""Tests for evidence-pack provenance completeness — тесты полноты (§23.29)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_common.provenance_completeness import (
    REQUIRED_SLOTS,
    ProvenanceReport,
    check,
)


def _full_provenance() -> dict[str, object]:
    """A provenance mapping with every REQUIRED_SLOT non-empty."""
    return {
        "model_version": "qwen2.5-7b",
        "prompt_version": "extract-v3",
        "extractor_run_id": "run-42",
        "graph_schema_version": "7",
        "data_snapshot_version": "2026-07-03",
        "retrieval_scores": [0.91, 0.42],
    }


def test_required_slots_canonical() -> None:
    assert REQUIRED_SLOTS == (
        "model_version",
        "prompt_version",
        "extractor_run_id",
        "graph_schema_version",
        "data_snapshot_version",
        "retrieval_scores",
    )


def test_all_present_is_complete() -> None:
    report = check(_full_provenance())
    assert isinstance(report, ProvenanceReport)
    assert report.complete is True
    assert report.completeness == 1.0
    assert report.missing == ()
    assert report.present == REQUIRED_SLOTS


def test_missing_prompt_version_listed() -> None:
    prov = _full_provenance()
    del prov["prompt_version"]
    report = check(prov)
    assert report.complete is False
    assert "prompt_version" in report.missing
    assert "prompt_version" not in report.present
    assert report.completeness == pytest.approx(5 / 6)


def test_empty_string_counts_as_missing() -> None:
    prov = _full_provenance()
    prov["model_version"] = ""
    report = check(prov)
    assert "model_version" in report.missing
    assert report.complete is False


def test_zero_int_counts_as_present() -> None:
    prov = _full_provenance()
    prov["graph_schema_version"] = 0
    report = check(prov)
    assert "graph_schema_version" in report.present
    assert "graph_schema_version" not in report.missing
    assert report.complete is True
    assert report.completeness == 1.0


def test_empty_collection_counts_as_missing() -> None:
    prov = _full_provenance()
    prov["retrieval_scores"] = []
    report = check(prov)
    assert "retrieval_scores" in report.missing
    assert report.complete is False


def test_all_missing_completeness_zero() -> None:
    report = check({})
    assert report.completeness == 0.0
    assert report.present == ()
    assert report.missing == REQUIRED_SLOTS
    assert report.complete is False


def test_missing_preserves_required_ordering() -> None:
    # Provide only the last slot; the rest are missing in canonical order.
    report = check({"retrieval_scores": [0.5]})
    assert report.missing == (
        "model_version",
        "prompt_version",
        "extractor_run_id",
        "graph_schema_version",
        "data_snapshot_version",
    )
    assert report.present == ("retrieval_scores",)


def test_custom_required_checks_only_given_slot() -> None:
    prov = {"model_version": "qwen2.5-7b"}
    report = check(prov, required=("model_version",))
    assert report.required == ("model_version",)
    assert report.present == ("model_version",)
    assert report.missing == ()
    assert report.complete is True
    assert report.completeness == 1.0


def test_custom_required_missing_slot() -> None:
    report = check({}, required=("model_version",))
    assert report.missing == ("model_version",)
    assert report.completeness == 0.0
    assert report.complete is False


def test_none_value_counts_as_missing() -> None:
    prov = _full_provenance()
    prov["extractor_run_id"] = None
    report = check(prov)
    assert "extractor_run_id" in report.missing


def test_as_dict_roundtrip() -> None:
    report = check(_full_provenance())
    d = report.as_dict()
    assert d == {
        "required": list(REQUIRED_SLOTS),
        "present": list(REQUIRED_SLOTS),
        "missing": [],
        "completeness": 1.0,
        "complete": True,
    }


def test_report_is_frozen() -> None:
    report = check(_full_provenance())
    with pytest.raises(FrozenInstanceError):
        report.completeness = 0.0  # type: ignore[misc]


def test_empty_required_completeness_zero() -> None:
    report = check(_full_provenance(), required=())
    assert report.completeness == 0.0
    assert report.present == ()
    assert report.missing == ()
    # Nothing required and nothing missing -> complete is vacuously True.
    assert report.complete is True
