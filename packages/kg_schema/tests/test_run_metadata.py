"""Tests for extractor run metadata (§6.14)."""

from __future__ import annotations

from kg_schema.provenance import REQUIRED_PROVENANCE, validate_provenance
from kg_schema.run_metadata import (
    DEFAULT_SCHEMA_VERSION,
    PROVENANCE_KEYS,
    RunMetadata,
    make_run_metadata,
)

# A fixed timestamp makes the deterministic run_id reproducible in assertions.
_TS = "2026-07-03T10:00:00+00:00"


def test_to_provenance_has_three_required_keys() -> None:
    md = make_run_metadata("llm", started_at=_TS, schema_version="1.4.0")
    prov = md.to_provenance()
    # Exactly the §3.7 obligation, matching kg_schema.provenance (drift guard).
    assert set(prov) == set(REQUIRED_PROVENANCE)
    assert set(prov) == set(PROVENANCE_KEYS)
    # And the mapping is run_id -> extractor_run_id, started_at -> created_at.
    assert prov["extractor_run_id"] == md.run_id
    assert prov["schema_version"] == "1.4.0"
    assert prov["created_at"] == _TS


def test_provenance_stamps_a_factual_node() -> None:
    # A Measurement stamped with to_provenance() is provenance-complete (§3.7).
    md = make_run_metadata("llm", started_at=_TS)
    node = {"label": "Measurement", "name": "Cu recovery 92%", **md.to_provenance()}
    check = validate_provenance(node)
    assert check.is_factual is True
    assert check.complete is True
    assert check.missing == []


def test_run_id_deterministic_for_same_inputs() -> None:
    a = make_run_metadata("llm", started_at=_TS)
    b = make_run_metadata("llm", started_at=_TS)
    # Same (extractor, started_at) -> byte-identical run_id, across calls.
    assert a.run_id == b.run_id
    assert a.run_id.startswith("run:")
    # A different extractor or timestamp changes the id.
    assert make_run_metadata("rule", started_at=_TS).run_id != a.run_id
    assert make_run_metadata("llm", started_at="2026-07-03T11:00:00+00:00").run_id != a.run_id


def test_as_dict_round_trip() -> None:
    md = make_run_metadata(
        "llm",
        started_at=_TS,
        extractor_version="2.1.0",
        model="qwen2.5",
        params={"temperature": 0.0},
        n_docs=3,
        n_entities=7,
        n_measurements=5,
    )
    d = md.as_dict()
    # Every field is present, and reconstructing yields an equal record.
    assert set(d) == {
        "run_id",
        "extractor",
        "extractor_version",
        "model",
        "params",
        "started_at",
        "schema_version",
        "n_docs",
        "n_entities",
        "n_measurements",
    }
    assert RunMetadata(**d) == md


def test_params_preserved_and_copied() -> None:
    params = {"temperature": 0.2, "prompt_id": "extract-v3"}
    md = make_run_metadata("llm", started_at=_TS, params=params)
    assert md.params == params
    # as_dict() hands back a copy: mutating it must not touch the frozen record.
    d = md.as_dict()
    d["params"]["temperature"] = 0.9
    assert md.params["temperature"] == 0.2


def test_defaults() -> None:
    md = RunMetadata(run_id="run:x", extractor="rule")
    assert md.extractor_version == "0.0.0"
    assert md.model is None
    assert md.params == {}
    assert md.started_at == ""
    assert md.schema_version == DEFAULT_SCHEMA_VERSION
    assert md.n_docs == 0
    assert md.n_entities == 0
    assert md.n_measurements == 0
    # Distinct instances do NOT share the default params dict (no mutable default).
    other = RunMetadata(run_id="run:y", extractor="rule")
    md.params["k"] = 1
    assert other.params == {}


def test_version_fields() -> None:
    md = make_run_metadata("llm", started_at=_TS, extractor_version="9.9.9", schema_version="2.0.0")
    assert md.extractor_version == "9.9.9"
    assert md.schema_version == "2.0.0"
    assert md.as_dict()["extractor_version"] == "9.9.9"
    assert md.as_dict()["schema_version"] == "2.0.0"
    # schema_version flows through to the stamped provenance.
    assert md.to_provenance()["schema_version"] == "2.0.0"


def test_counts() -> None:
    md = make_run_metadata("llm", started_at=_TS, n_docs=12, n_entities=340, n_measurements=88)
    assert (md.n_docs, md.n_entities, md.n_measurements) == (12, 340, 88)
    d = md.as_dict()
    assert (d["n_docs"], d["n_entities"], d["n_measurements"]) == (12, 340, 88)


def test_make_run_metadata_fills_started_at_and_default_schema() -> None:
    md = make_run_metadata("llm")
    # started_at auto-filled with a non-empty ISO-8601 UTC timestamp.
    assert md.started_at
    assert md.started_at.endswith("+00:00")
    assert md.run_id == make_run_metadata("llm", started_at=md.started_at).run_id
    # schema_version falls back to the module default when unspecified.
    assert md.schema_version == DEFAULT_SCHEMA_VERSION
