"""Тесты разбора вложений сообщения чата / chat-message attachment parsing tests (§14.4)."""

from __future__ import annotations

import pytest
from api_gateway.chat_attachments import (
    ChatAttachments,
    is_empty,
    merge,
    parse_attachments,
)


def test_none_is_empty() -> None:
    """``None`` → пустые вложения, ``is_empty`` истинно / None yields empty attachments."""
    a = parse_attachments(None)
    assert a == ChatAttachments()
    assert a.node_ids == ()
    assert a.doc_ids == ()
    assert a.subgraph is None
    assert is_empty(a) is True


def test_empty_mapping_is_empty() -> None:
    """Пустой mapping тоже пуст / an empty mapping is empty too."""
    assert is_empty(parse_attachments({})) is True


def test_node_ids_dedupe_preserves_order() -> None:
    """``node_ids`` дедуплицируются с сохранением порядка / dedupe preserving order."""
    a = parse_attachments({"node_ids": ["n1", "n1", "n2"]})
    assert a.node_ids == ("n1", "n2")
    assert is_empty(a) is False


def test_doc_ids_dedupe_preserves_order() -> None:
    """``doc_ids`` тоже дедуплицируются / doc_ids dedupe as well."""
    a = parse_attachments({"doc_ids": ["d1", "d2", "d1", "d3"]})
    assert a.doc_ids == ("d1", "d2", "d3")


def test_node_ids_non_str_raises() -> None:
    """Не-строка в списке → ValueError / a non-str element raises."""
    with pytest.raises(ValueError):
        parse_attachments({"node_ids": [1]})


def test_node_ids_bool_raises() -> None:
    """``bool`` (подкласс int) недопустим / bool is rejected though it subclasses int."""
    with pytest.raises(ValueError):
        parse_attachments({"node_ids": [True]})


def test_node_ids_not_a_list_raises() -> None:
    """Строка вместо списка → ValueError / a bare string is not a list."""
    with pytest.raises(ValueError):
        parse_attachments({"node_ids": "n1"})


def test_doc_ids_not_a_list_raises() -> None:
    """``doc_ids`` не список → ValueError / doc_ids must be a list."""
    with pytest.raises(ValueError):
        parse_attachments({"doc_ids": {"a": 1}})


def test_subgraph_passthrough() -> None:
    """``subgraph`` передаётся как есть / subgraph is stored verbatim."""
    a = parse_attachments({"subgraph": {"nodes": []}})
    assert a.subgraph == {"nodes": []}
    assert is_empty(a) is False


def test_subgraph_wrong_type_raises() -> None:
    """``subgraph`` не dict → ValueError / a non-dict subgraph raises."""
    with pytest.raises(ValueError):
        parse_attachments({"subgraph": [1, 2, 3]})


def test_raw_not_mapping_raises() -> None:
    """Не-mapping payload → ValueError / a non-mapping payload raises."""
    with pytest.raises(ValueError):
        parse_attachments([1, 2])  # type: ignore[arg-type]


def test_merge_node_ids_union() -> None:
    """merge объединяет ``node_ids`` с сохранением порядка / union preserves order."""
    m = merge(parse_attachments({"node_ids": ["a"]}), parse_attachments({"node_ids": ["b"]}))
    assert m.node_ids == ("a", "b")


def test_merge_dedupes_across_inputs() -> None:
    """merge убирает дубли между входами / merge dedupes across a and b."""
    m = merge(
        parse_attachments({"node_ids": ["a", "b"], "doc_ids": ["d1"]}),
        parse_attachments({"node_ids": ["b", "c"], "doc_ids": ["d1", "d2"]}),
    )
    assert m.node_ids == ("a", "b", "c")
    assert m.doc_ids == ("d1", "d2")


def test_merge_b_subgraph_wins() -> None:
    """subgraph из ``b`` побеждает, если задан / b's subgraph wins when set."""
    a = ChatAttachments(subgraph={"src": "a"})
    b = ChatAttachments(subgraph={"src": "b"})
    assert merge(a, b).subgraph == {"src": "b"}


def test_merge_keeps_a_subgraph_when_b_none() -> None:
    """subgraph из ``a`` сохраняется, если у ``b`` нет / a's subgraph kept when b is None."""
    a = ChatAttachments(subgraph={"src": "a"})
    b = ChatAttachments()
    assert merge(a, b).subgraph == {"src": "a"}


def test_as_dict_keys() -> None:
    """as_dict содержит ровно нужные ключи / as_dict exposes exactly the three keys."""
    d = parse_attachments({"node_ids": ["n1"], "subgraph": {"x": 1}, "doc_ids": ["d1"]}).as_dict()
    assert set(d) == {"node_ids", "subgraph", "doc_ids"}
    assert d["node_ids"] == ["n1"]
    assert d["subgraph"] == {"x": 1}
    assert d["doc_ids"] == ["d1"]


def test_full_roundtrip() -> None:
    """Полный разбор всех полот сразу / a full payload parses all three fields."""
    a = parse_attachments(
        {"node_ids": ["n1", "n2", "n1"], "subgraph": {"nodes": [1]}, "doc_ids": ["d1"]}
    )
    assert a.node_ids == ("n1", "n2")
    assert a.subgraph == {"nodes": [1]}
    assert a.doc_ids == ("d1",)
    assert is_empty(a) is False
