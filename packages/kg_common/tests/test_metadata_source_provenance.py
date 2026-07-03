"""Tests for the source-provenance assembler — тесты сборки происхождения (§10.10)."""

from __future__ import annotations

from kg_common.metadata.source_provenance import (
    SourceProvenance,
    assemble_provenance,
    is_stale,
)

_ACCEPTED = {
    "source_id": "s",
    "owner": "o",
    "lab": "L",
    "version": 2,
    "freshness": "2026-01",
    "review_status": "accepted",
}


def test_assemble_pulls_source_fields() -> None:
    p = assemble_provenance(_ACCEPTED)
    assert p.owner == "o"
    assert p.version == 2
    assert p.lab == "L"
    assert p.freshness == "2026-01"
    assert p.review_status == "accepted"
    assert p.source_id == "s"
    # No run given → extractor/model/run-id default to empty.
    assert p.extractor == ""
    assert p.model == ""
    assert p.mlflow_run_id == ""


def test_assemble_pulls_run_fields() -> None:
    run = {"extractor": "e", "model": "m", "mlflow_run_id": "r"}
    p = assemble_provenance(_ACCEPTED, run)
    assert p.model == "m"
    assert p.extractor == "e"
    assert p.mlflow_run_id == "r"


def test_run_wins_over_source() -> None:
    src = {**_ACCEPTED, "model": "src-model", "mlflow_run_id": "src-run"}
    p = assemble_provenance(src, {"model": "run-model", "mlflow_run_id": "run-run"})
    assert p.model == "run-model"
    assert p.mlflow_run_id == "run-run"


def test_defaults_for_missing_fields() -> None:
    p = assemble_provenance({"source_id": "s"})
    assert p.owner == ""
    assert p.lab == ""
    assert p.version == 0
    assert p.freshness == ""
    assert p.review_status == ""
    assert p.data_version == ""


def test_to_citation_projection() -> None:
    p = assemble_provenance(_ACCEPTED)
    cit = p.to_citation()
    assert cit["owner"] == "o"
    assert cit["version"] == 2
    assert cit["lab"] == "L"
    assert cit["freshness"] == "2026-01"
    assert cit["mlflow_run_id"] == ""
    assert cit["data_version"] == ""
    # Internal fields never leak into a citation.
    assert "extractor" not in cit
    assert "model" not in cit
    assert "review_status" not in cit
    assert "source_id" not in cit


def test_to_citation_carries_run_id_and_data_version() -> None:
    src = {**_ACCEPTED, "data_version": "dv7"}
    p = assemble_provenance(src, {"mlflow_run_id": "r"})
    cit = p.to_citation()
    assert cit["mlflow_run_id"] == "r"
    assert cit["data_version"] == "dv7"


def test_as_dict_is_full_record() -> None:
    p = assemble_provenance(_ACCEPTED, {"extractor": "e", "model": "m"})
    d = p.as_dict()
    assert d["source_id"] == "s"
    assert d["extractor"] == "e"
    assert d["model"] == "m"
    assert d["review_status"] == "accepted"
    assert set(d) == {
        "source_id",
        "owner",
        "lab",
        "version",
        "freshness",
        "extractor",
        "model",
        "review_status",
        "mlflow_run_id",
        "data_version",
    }


def test_is_stale_within_window_and_accepted_is_false() -> None:
    p = assemble_provenance(_ACCEPTED)
    assert is_stale(p, 10, 30) is False


def test_is_stale_aged_out_is_true() -> None:
    p = assemble_provenance(_ACCEPTED)
    assert is_stale(p, 40, 30) is True


def test_is_stale_boundary_equal_is_false() -> None:
    p = assemble_provenance(_ACCEPTED)
    # age_days == max_age_days is not strictly greater → fresh.
    assert is_stale(p, 30, 30) is False


def test_is_stale_not_accepted_is_true() -> None:
    p = assemble_provenance({"source_id": "s", "review_status": "pending"})
    assert is_stale(p, 1, 30) is True


def test_is_stale_not_accepted_even_when_fresh() -> None:
    p = assemble_provenance({"source_id": "s", "review_status": ""})
    assert is_stale(p, 0, 30) is True


def test_frozen_dataclass_is_immutable() -> None:
    p = SourceProvenance(
        source_id="s",
        owner="o",
        lab="L",
        version=2,
        freshness="2026-01",
        extractor="e",
        model="m",
        review_status="accepted",
    )
    try:
        p.owner = "x"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("SourceProvenance must be frozen")
