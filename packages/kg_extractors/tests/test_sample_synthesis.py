"""Sample-node synthesis (§6.13)."""

from __future__ import annotations

from dataclasses import dataclass

from kg_extractors.sample_synthesis import (
    Sample,
    make_sample_id,
    sample_edges,
    synthesize_samples,
)


@dataclass
class _Rec:
    """Object-style record (exercises the non-Mapping accessor path)."""

    experiment_id: str | None = None
    material_id: str | None = None
    regime_id: str | None = None
    measurement_id: str | None = None
    doc_id: str | None = None


def test_same_triplet_is_deterministic_and_idempotent() -> None:
    r1 = {"experiment_id": "exp1", "material_id": "mat1", "regime_id": "reg1", "doc_id": "d1"}
    r2 = {"experiment_id": "exp1", "material_id": "mat1", "regime_id": "reg1", "doc_id": "d1"}
    samples = synthesize_samples([r1, r2])
    assert len(samples) == 1
    # Concrete, hand-checkable id: sha1("exp1|mat1|reg1")[:12].
    assert samples[0].sample_id == "sample:497244d39b72"
    # Idempotent: the id function reproduces it exactly on a re-run.
    assert make_sample_id("exp1", "mat1", "reg1") == "sample:497244d39b72"
    assert synthesize_samples([r1])[0].sample_id == samples[0].sample_id


def test_different_regime_yields_different_id() -> None:
    base = {"experiment_id": "exp1", "material_id": "mat1"}
    reg1 = {**base, "regime_id": "reg1", "measurement_id": "m1"}
    reg2 = {**base, "regime_id": "reg2", "measurement_id": "m2"}
    samples = synthesize_samples([reg1, reg2])
    assert len(samples) == 2
    assert samples[0].sample_id == "sample:497244d39b72"
    assert samples[1].sample_id == "sample:7a69d78bd3a1"
    assert samples[0].sample_id != samples[1].sample_id


def test_measurement_ids_aggregated_ordered_and_deduped() -> None:
    triplet = {"experiment_id": "exp1", "material_id": "mat1", "regime_id": "reg1"}
    recs = [
        {**triplet, "measurement_id": "m1"},
        {**triplet, "measurement_id": "m2"},
        {**triplet, "measurement_id": "m1"},  # duplicate -> collapsed
        {**triplet, "measurement_ids": ["m2", "m3"]},  # list form supported
    ]
    samples = synthesize_samples(recs)
    assert len(samples) == 1
    assert samples[0].measurement_ids == ("m1", "m2", "m3")


def test_edges_cover_the_four_link_types() -> None:
    rec = {
        "experiment_id": "exp1",
        "material_id": "mat1",
        "regime_id": "reg1",
        "measurement_id": "m1",
    }
    sample = synthesize_samples([rec])[0]
    edges = sample_edges(sample)
    assert [e["type"] for e in edges] == [
        "HAS_SAMPLE",
        "OF_MATERIAL",
        "UNDER_REGIME",
        "HAS_MEASUREMENT",
    ]
    by_type = {e["type"]: e for e in edges}
    assert by_type["HAS_SAMPLE"] == {
        "source": "exp1",
        "target": "sample:497244d39b72",
        "type": "HAS_SAMPLE",
        "from_label": "Experiment",
        "to_label": "Sample",
    }
    assert by_type["OF_MATERIAL"]["source"] == "sample:497244d39b72"
    assert by_type["OF_MATERIAL"]["target"] == "mat1"
    assert by_type["UNDER_REGIME"]["target"] == "reg1"
    assert by_type["HAS_MEASUREMENT"]["target"] == "m1"


def test_multiple_measurements_emit_multiple_has_measurement_edges() -> None:
    triplet = {"experiment_id": "exp1", "material_id": "mat1", "regime_id": "reg1"}
    sample = synthesize_samples([{**triplet, "measurement_ids": ["m1", "m2"]}])[0]
    has_meas = [e for e in sample_edges(sample) if e["type"] == "HAS_MEASUREMENT"]
    assert [e["target"] for e in has_meas] == ["m1", "m2"]


def test_missing_material_is_graceful() -> None:
    rec = {"experiment_id": "exp1", "regime_id": "reg1", "measurement_id": "m1"}
    samples = synthesize_samples([rec])
    assert len(samples) == 1
    sample = samples[0]
    assert sample.material_id is None
    # A material-less specimen still gets a stable, deterministic id.
    assert sample.sample_id == "sample:8f5d4326323f"
    assert make_sample_id("exp1", None, "reg1") == "sample:8f5d4326323f"
    # No OF_MATERIAL edge is emitted for a nonexistent material.
    assert [e["type"] for e in sample_edges(sample)] == [
        "HAS_SAMPLE",
        "UNDER_REGIME",
        "HAS_MEASUREMENT",
    ]


def test_doc_id_preserved_first_non_none() -> None:
    triplet = {"experiment_id": "exp1", "material_id": "mat1", "regime_id": "reg1"}
    recs = [
        {**triplet, "doc_id": None, "measurement_id": "m1"},
        {**triplet, "doc_id": "doc-42", "measurement_id": "m2"},
        {**triplet, "doc_id": "doc-99", "measurement_id": "m3"},
    ]
    samples = synthesize_samples(recs)
    assert samples[0].doc_id == "doc-42"


def test_as_dict_exact() -> None:
    rec = _Rec(
        experiment_id="exp1",
        material_id="mat1",
        regime_id="reg1",
        measurement_id="m1",
        doc_id="d1",
    )
    sample = synthesize_samples([rec])[0]
    assert isinstance(sample, Sample)
    assert sample.as_dict() == {
        "sample_id": "sample:497244d39b72",
        "experiment_id": "exp1",
        "material_id": "mat1",
        "regime_id": "reg1",
        "measurement_ids": ["m1"],
        "doc_id": "d1",
    }


def test_empty_input_returns_empty() -> None:
    assert synthesize_samples([]) == []


def test_object_records_supported_like_dicts() -> None:
    recs = [
        _Rec(experiment_id="expA", material_id="matA", regime_id="regA", measurement_id="m1"),
        _Rec(experiment_id="expA", material_id="matA", regime_id="regA", measurement_id="m2"),
    ]
    samples = synthesize_samples(recs)
    assert len(samples) == 1
    assert samples[0].sample_id == "sample:584288b3513b"
    assert samples[0].measurement_ids == ("m1", "m2")
