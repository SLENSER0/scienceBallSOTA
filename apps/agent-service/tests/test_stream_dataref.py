"""§13.22 tests for ``dataRef`` pointers / тесты указателей на данные.

Hand-checkable assertions over :mod:`agent_service.stream_dataref`: determinism, payload
sensitivity, kind validation, size counting, bulk detection, prefix shape, and ref equality.
"""

from __future__ import annotations

import pytest
from agent_service.stream_dataref import (
    DataRef,
    is_bulky,
    make_dataref,
    same_ref,
)


def test_deterministic_same_kind_and_payload() -> None:
    """(1) Same kind + payload → identical ref across two calls / детерминизм."""
    payload = {"nodes": [3, 1, 2], "edges": [{"a": 1, "b": 2}]}
    first = make_dataref("graph", payload)
    second = make_dataref("graph", payload)
    assert first.ref == second.ref
    # Sorted-key canonical JSON: key order in the dict must not change the ref.
    reordered = {"edges": [{"b": 2, "a": 1}], "nodes": [3, 1, 2]}
    assert make_dataref("graph", reordered).ref == first.ref


def test_different_payload_different_ref() -> None:
    """(2) A different payload yields a different ref / разные данные → разный ref."""
    a = make_dataref("table", [1, 2, 3])
    b = make_dataref("table", [1, 2, 4])
    assert a.ref != b.ref


def test_unknown_kind_raises() -> None:
    """(3) kind='foo' raises ValueError / неизвестный вид → ValueError."""
    with pytest.raises(ValueError):
        make_dataref("foo", [1, 2, 3])


def test_size_of_three_element_list() -> None:
    """(4) size for a 3-element list is 3 / размер списка из трёх — 3."""
    ref = make_dataref("evidence", ["x", "y", "z"])
    assert ref.size == 3
    # dict counts its keys; a scalar is size 1.
    assert make_dataref("evidence", {"a": 1, "b": 2}).size == 2
    assert make_dataref("evidence", "scalar").size == 1


def test_is_bulky_threshold() -> None:
    """(5) is_bulky True for 25 items at threshold 20, False for 5 / порог объёма."""
    assert is_bulky(list(range(25)), threshold=20) is True
    assert is_bulky(list(range(5)), threshold=20) is False
    # Boundary: exactly at threshold is not bulky (strict >).
    assert is_bulky(list(range(20)), threshold=20) is False
    # Scalars have no length → never bulky.
    assert is_bulky(42) is False


def test_ref_starts_with_kind_prefix() -> None:
    """(6) ref starts with the kind prefix followed by ':' / префикс вида."""
    ref = make_dataref("gaps", [{"gap": 1}])
    assert ref.ref.startswith("gaps:")
    prefix, _, digest = ref.ref.partition(":")
    assert prefix == "gaps"
    assert len(digest) == 12


def test_same_ref_and_as_dict() -> None:
    """(7) same_ref True for equal ref strings; as_dict exposes ref/kind/size."""
    original = make_dataref("graph", [1, 2, 3])
    twin = DataRef(ref=original.ref, kind="graph", size=original.size)
    assert same_ref(original, twin) is True
    other = make_dataref("graph", [9, 9, 9])
    assert same_ref(original, other) is False

    d = original.as_dict()
    assert d == {"ref": original.ref, "kind": "graph", "size": 3}
    assert set(d) == {"ref", "kind", "size"}
