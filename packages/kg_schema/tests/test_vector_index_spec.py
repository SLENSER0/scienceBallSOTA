"""Vector index spec for node embeddings (§3.13)."""

from __future__ import annotations

from kg_schema.vector_index_spec import (
    ENTITY_EMBEDDING_INDEX,
    VectorIndexSpec,
    cosine,
    self_nearest,
    validate_embedding,
)


def test_pinned_index_dimensions_and_similarity() -> None:
    assert ENTITY_EMBEDDING_INDEX.dimensions == 1024
    assert ENTITY_EMBEDDING_INDEX.similarity == "cosine"
    assert ENTITY_EMBEDDING_INDEX.name == "entity_embedding_index"
    assert ENTITY_EMBEDDING_INDEX.label == "Entity"
    assert ENTITY_EMBEDDING_INDEX.property == "embedding"


def test_to_cypher_contains_expected_fragments() -> None:
    ddl = ENTITY_EMBEDDING_INDEX.to_cypher()
    assert "CREATE VECTOR INDEX entity_embedding_index" in ddl
    assert "vector.dimensions`: 1024" in ddl
    assert "'cosine'" in ddl


def test_as_dict_roundtrip() -> None:
    d = ENTITY_EMBEDDING_INDEX.as_dict()
    assert d["dimensions"] == 1024
    assert d["similarity"] == "cosine"
    assert d["name"] == "entity_embedding_index"
    assert d["label"] == "Entity"
    assert d["property"] == "embedding"


def test_frozen_dataclass() -> None:
    spec = VectorIndexSpec("x", "L", "p", 4, "cosine")
    try:
        spec.dimensions = 8  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("VectorIndexSpec must be frozen")


def test_validate_embedding_ok() -> None:
    ok, errors = validate_embedding([1.0] * 1024)
    assert ok is True
    assert errors == []


def test_validate_embedding_wrong_length() -> None:
    ok, errors = validate_embedding([1.0] * 3)
    assert ok is False
    assert errors


def test_validate_embedding_non_finite() -> None:
    ok, _ = validate_embedding([float("nan")] * 1024)
    assert ok is False
    ok_inf, _ = validate_embedding([float("inf")] * 1024)
    assert ok_inf is False


def test_validate_embedding_custom_spec() -> None:
    spec = VectorIndexSpec("t", "L", "e", 2, "cosine")
    assert validate_embedding([0.1, 0.2], spec) == (True, [])
    assert validate_embedding([0.1], spec)[0] is False


def test_cosine_identical_and_orthogonal() -> None:
    assert abs(cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9
    assert abs(cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_zero_vector_safe() -> None:
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_self_nearest_argmax() -> None:
    v = [1.0, 0.0]
    assert self_nearest(v, {"a": v, "b": [0.0, 1.0]}) == "a"
