"""Dagster-style partitioning helper tests (§9.3)."""

from __future__ import annotations

import pytest

from kg_common.partitions import (
    PartitionSet,
    by_document_partition,
    by_source_partition,
    monthly_partitions,
    partition_key_for,
    static_partitions,
)


def test_by_document_partition_keys_match_inputs() -> None:
    # Inputs are already valid slugs, so keys equal the inputs verbatim.
    ps = by_document_partition(["doc-1", "doc-2", "doc-3"])
    assert isinstance(ps, PartitionSet)
    assert ps.name == "by_document"
    assert ps.keys == ("doc-1", "doc-2", "doc-3")


def test_partition_key_for_is_stable_and_slugged() -> None:
    key = partition_key_for("doc:Al-Cu 2024")
    assert key == "doc-al-cu-2024"
    # Deterministic — same input, same key; distinct inputs, distinct keys.
    assert partition_key_for("doc:Al-Cu 2024") == key
    assert partition_key_for("doc:Al-Cu 2025") != key


def test_monthly_partitions_wraps_year() -> None:
    ps = monthly_partitions(2023, 11, 4)
    assert ps.name == "monthly"
    assert ps.keys == ("2023-11", "2023-12", "2024-01", "2024-02")


def test_monthly_partitions_long_span_and_zero_padding() -> None:
    ps = monthly_partitions(2019, 1, 14)
    assert len(ps.keys) == 14
    assert ps.keys[0] == "2019-01"
    assert ps.keys[11] == "2019-12"
    assert ps.keys[12] == "2020-01"
    assert ps.keys[13] == "2020-02"


def test_by_source_partition() -> None:
    ps = by_source_partition(["src-a", "src-b"])
    assert ps.name == "by_source"
    assert ps.keys == ("src-a", "src-b")


def test_as_dict_shape() -> None:
    ps = static_partitions(["k1", "k2"])
    assert ps.as_dict() == {"name": "static", "keys": ["k1", "k2"]}
    # keys must be a plain list (JSON-friendly), not a tuple.
    assert isinstance(ps.as_dict()["keys"], list)


def test_keys_are_deduplicated_in_first_seen_order() -> None:
    assert static_partitions(["a", "b", "a", "c", "b"]).keys == ("a", "b", "c")
    # De-dup also applies to document/source builders (same doc id twice).
    assert by_document_partition(["doc-1", "doc-1", "doc-2"]).keys == ("doc-1", "doc-2")


def test_empty_inputs() -> None:
    assert static_partitions([]).keys == ()
    assert by_document_partition([]).keys == ()
    assert monthly_partitions(2024, 6, 0).keys == ()
    assert monthly_partitions(2024, 6, 0).as_dict() == {"name": "monthly", "keys": []}


def test_invalid_arguments_raise() -> None:
    with pytest.raises(ValueError):
        monthly_partitions(2024, 0, 3)
    with pytest.raises(ValueError):
        monthly_partitions(2024, 13, 3)
    with pytest.raises(ValueError):
        monthly_partitions(2024, 6, -1)
