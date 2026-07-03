"""Tests for NDJSON entity/edge serialisation — тесты потока NDJSON (§22)."""

from __future__ import annotations

from kg_common.ndjson_export import (
    NdjsonRecord,
    edge_record,
    entity_record,
    iter_ndjson,
    to_ndjson,
)


def test_single_node_one_newline_terminated_line() -> None:
    """One node -> exactly one line ending in a single ``\\n``."""
    text = to_ndjson([entity_record({"id": "n1", "name": "Iron"})])
    assert text.endswith("\n")
    assert text.count("\n") == 1
    # Strip the sole terminator -> no interior newlines remain.
    assert "\n" not in text[:-1]


def test_parsed_object_has_node_kind() -> None:
    """Parsed object carries the ``kind == 'node'`` discriminator."""
    parsed = iter_ndjson(to_ndjson([entity_record({"id": "n1"})]))
    assert len(parsed) == 1
    assert parsed[0]["kind"] == "node"
    assert parsed[0]["id"] == "n1"


def test_edge_record_kind() -> None:
    """``edge_record`` produces a ``kind == 'edge'`` object."""
    rec = edge_record({"src": "a", "dst": "b"})
    assert rec.kind == "edge"
    parsed = iter_ndjson(to_ndjson([rec]))
    assert parsed[0]["kind"] == "edge"
    assert parsed[0]["src"] == "a"


def test_keys_emitted_sorted() -> None:
    """``sort_keys=True``: ``"id"`` is emitted before ``"name"`` (and kind)."""
    line = to_ndjson([entity_record({"name": "Iron", "id": "n1"})]).rstrip("\n")
    # Sorted order: id < kind < name.
    assert line.index('"id"') < line.index('"kind"') < line.index('"name"')


def test_cyrillic_round_trips_unescaped() -> None:
    """``ensure_ascii=False``: Cyrillic value passes through verbatim."""
    text = to_ndjson([entity_record({"id": "n1", "name": "Железо"})])
    assert "Железо" in text  # not \u-escaped
    assert iter_ndjson(text)[0]["name"] == "Железо"


def test_empty_iterable_is_empty_string() -> None:
    """No records -> ``''`` with no trailing newline."""
    assert to_ndjson([]) == ""
    assert iter_ndjson("") == []


def test_payload_kind_does_not_override_discriminator() -> None:
    """A payload ``kind`` key cannot clobber the reserved discriminator."""
    rec = entity_record({"id": "n1", "kind": "attacker"})
    assert rec.as_dict()["kind"] == "node"
    parsed = iter_ndjson(to_ndjson([rec]))
    assert parsed[0]["kind"] == "node"


def test_iter_ndjson_ignores_trailing_blank_line() -> None:
    """Two records -> two lines; a trailing blank line is skipped, len == 2."""
    text = to_ndjson([entity_record({"id": "n1"}), edge_record({"src": "n1", "dst": "n2"})])
    assert text.endswith("\n")
    parsed = iter_ndjson(text)
    assert len(parsed) == 2
    assert [p["kind"] for p in parsed] == ["node", "edge"]


def test_iter_ndjson_skips_interior_blank_lines() -> None:
    """Blank/whitespace-only lines anywhere are ignored on parse."""
    text = '{"id": "n1", "kind": "node"}\n\n   \n{"kind": "edge", "src": "a"}\n'
    parsed = iter_ndjson(text)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "n1"
    assert parsed[1]["src"] == "a"


def test_round_trip_payload_equality() -> None:
    """``to_ndjson`` then ``iter_ndjson`` round-trips payload data."""
    records = [
        entity_record({"id": "n1", "name": "Железо", "props": {"z": 26}}),
        edge_record({"src": "n1", "dst": "n2", "rel": "bonds", "weight": 3}),
    ]
    parsed = iter_ndjson(to_ndjson(records))
    for record, obj in zip(records, parsed, strict=True):
        assert obj == record.as_dict()


def test_as_dict_matches_expected_shape() -> None:
    """``as_dict`` merges payload under the ``kind`` discriminator."""
    rec = NdjsonRecord(kind="node", payload={"id": "n1", "name": "Iron"})
    assert rec.as_dict() == {"id": "n1", "name": "Iron", "kind": "node"}
