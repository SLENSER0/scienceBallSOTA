"""Tests for the parsed document page block render model (§17.19/§17.13).

Проверяем сортировку по input order, плотный 0-based order, нормализацию
``kind``, формат якоря, единственную подсветку и round-trip ``highlightId=None``.
"""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.document_page_view import (
    PageBlock,
    PageView,
    build_page_view,
)


def _raw(block_id: str, order: int, kind: str = "paragraph", text: str = "") -> dict:
    """Собрать сырой блок для краткости тестов."""
    return {"block_id": block_id, "order": order, "kind": kind, "text": text}


def test_blocks_sorted_by_input_order() -> None:
    """(1) input [order=2, order=1] → первым идёт блок с order=1."""
    view = build_page_view(
        "doc1",
        3,
        [_raw("b2", 2), _raw("b1", 1)],
    )
    assert [b.block_id for b in view.blocks] == ["b1", "b2"]


def test_dense_order_reassigned() -> None:
    """(2) плотный 0-based order: 0,1,2 независимо от input order."""
    view = build_page_view(
        "doc1",
        1,
        [_raw("c", 50), _raw("a", 10), _raw("b", 30)],
    )
    assert [b.order for b in view.blocks] == [0, 1, 2]
    assert [b.block_id for b in view.blocks] == ["a", "b", "c"]


def test_kind_table_normalised() -> None:
    """(3) kind 'Table' нормализуется в 'table'."""
    view = build_page_view("doc1", 1, [_raw("t1", 0, kind="Table")])
    assert view.blocks[0].kind == "table"


def test_unknown_kind_falls_back_to_paragraph() -> None:
    """(4) неизвестный kind 'caption' → 'paragraph'."""
    view = build_page_view("doc1", 1, [_raw("x1", 0, kind="caption")])
    assert view.blocks[0].kind == "paragraph"


def test_figure_anchor_format() -> None:
    """(5) anchor блока-рисунка 'f3' == 'figure:f3'."""
    view = build_page_view("doc1", 1, [_raw("f3", 0, kind="figure")])
    assert view.blocks[0].anchor == "figure:f3"


def test_highlight_sets_exactly_one() -> None:
    """(6) highlight_id='p2' подсвечивает ровно этот блок, остальные — нет."""
    view = build_page_view(
        "doc1",
        1,
        [_raw("p1", 0), _raw("p2", 1), _raw("p3", 2)],
        highlight_id="p2",
    )
    flags = {b.block_id: b.highlighted for b in view.blocks}
    assert flags == {"p1": False, "p2": True, "p3": False}
    assert view.highlight_id == "p2"


def test_no_highlight_all_false() -> None:
    """Без highlight_id ни один блок не подсвечен."""
    view = build_page_view("doc1", 1, [_raw("p1", 0), _raw("p2", 1)])
    assert all(not b.highlighted for b in view.blocks)


def test_as_dict_camel_case_and_highlight_none_round_trip() -> None:
    """(7) PageView.as_dict()['highlightId'] round-trips None; ключи camelCase."""
    view = build_page_view("docABC", 4, [_raw("p1", 0, kind="figure", text="hi")])
    d = view.as_dict()
    assert d["docId"] == "docABC"
    assert d["page"] == 4
    assert d["highlightId"] is None
    block = d["blocks"][0]
    assert set(block) == {"blockId", "kind", "order", "text", "anchor", "highlighted"}
    assert block["blockId"] == "p1"
    assert block["kind"] == "figure"
    assert block["anchor"] == "figure:p1"
    assert block["text"] == "hi"


def test_block_and_view_are_frozen() -> None:
    """PageBlock и PageView неизменяемы (frozen)."""
    view = build_page_view("doc1", 1, [_raw("p1", 0)])
    block = view.blocks[0]
    assert dataclasses.is_dataclass(block)
    assert isinstance(view, PageView)
    assert isinstance(block, PageBlock)
    with pytest.raises(dataclasses.FrozenInstanceError):
        block.text = "changed"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.page = 9  # type: ignore[misc]


def test_missing_order_defaults_to_zero() -> None:
    """Блок без ключа order сортируется как order=0 (стабильно)."""
    view = build_page_view("doc1", 1, [{"block_id": "a"}, _raw("b", 5)])
    assert [b.block_id for b in view.blocks] == ["a", "b"]
    assert view.blocks[0].kind == "paragraph"
    assert view.blocks[0].text == ""
