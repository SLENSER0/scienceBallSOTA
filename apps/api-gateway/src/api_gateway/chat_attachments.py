"""Разбор и валидация вложений сообщения чата (§14.4 / §5.2.3).

Модуль на чистом stdlib для тела ``POST /chat/sessions/{id}/messages``. Поле
``attachments`` переносит выбранные ``node_ids`` из графа, подграф-«лассо»
(:data:`subgraph`) и ``doc_ids`` документов. ``routers/chat.py`` принимает
``attachments`` нетипизированно и парсера не существует — здесь он появляется.

Pure-stdlib parser for the ``attachments`` payload of the
``POST /chat/sessions/{id}/messages`` body (§5.2.3). ``attachments`` carries the
selected graph ``node_ids``, a lasso ``subgraph`` and document ``doc_ids``.
``routers/chat.py`` accepts ``attachments`` untyped with no parser — this module
supplies one.

* :class:`ChatAttachments` — frozen ``(node_ids, subgraph, doc_ids)`` c :meth:`as_dict`.
* :func:`parse_attachments` — сырой payload → :class:`ChatAttachments` / raw → dataclass.
* :func:`is_empty` — вложения пусты? / are the attachments empty?
* :func:`merge` — объединение двух вложений / order-preserving union of two attachments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ChatAttachments:
    """Неизменяемые вложения сообщения / immutable chat-message attachments (§5.2.3)."""

    node_ids: tuple[str, ...] = ()
    subgraph: dict[str, Any] | None = None
    doc_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Сериализация в словарь / serialise to a plain dict."""
        return {
            "node_ids": list(self.node_ids),
            "subgraph": self.subgraph,
            "doc_ids": list(self.doc_ids),
        }


def _dedupe(ids: tuple[str, ...]) -> tuple[str, ...]:
    """Убрать дубли, сохраняя порядок / drop duplicates preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return tuple(out)


def _parse_id_list(raw: Any, field: str) -> tuple[str, ...]:
    """Провалидировать список строковых id / validate a list-of-str id field.

    Поднимает :class:`ValueError` если ``raw`` не список или содержит не-строку /
    raises :class:`ValueError` when ``raw`` is not a list or holds a non-``str``.
    Дедуплицирует, сохраняя порядок / dedupes preserving order.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be a list, got {type(raw).__name__}")
    for item in raw:
        # ``bool`` — подкласс ``int``, но здесь недопустим / bool is an int subclass: reject.
        if not isinstance(item, str) or isinstance(item, bool):
            raise ValueError(f"{field} must contain only str, got {type(item).__name__}")
    return _dedupe(tuple(raw))


def parse_attachments(raw: Mapping[str, Any] | None) -> ChatAttachments:
    """Разобрать сырой payload вложений / parse the raw ``attachments`` payload (§5.2.3).

    ``None`` (или пустой mapping) → пустые вложения / empty attachments. ``node_ids``
    и ``doc_ids`` должны быть списками строк (иначе :class:`ValueError`) и
    дедуплицируются с сохранением порядка. ``subgraph`` передаётся как есть.
    """
    if raw is None:
        return ChatAttachments()
    if not isinstance(raw, Mapping):
        raise ValueError(f"attachments must be a mapping, got {type(raw).__name__}")
    node_ids = _parse_id_list(raw.get("node_ids"), "node_ids")
    doc_ids = _parse_id_list(raw.get("doc_ids"), "doc_ids")
    subgraph = raw.get("subgraph")
    if subgraph is not None and not isinstance(subgraph, dict):
        raise ValueError(f"subgraph must be a dict or null, got {type(subgraph).__name__}")
    return ChatAttachments(node_ids=node_ids, subgraph=subgraph, doc_ids=doc_ids)


def is_empty(a: ChatAttachments) -> bool:
    """Пусты ли вложения? / are the attachments empty (no ids and no subgraph)?"""
    return not a.node_ids and not a.doc_ids and a.subgraph is None


def merge(a: ChatAttachments, b: ChatAttachments) -> ChatAttachments:
    """Объединить два вложения / order-preserving union of two attachments.

    ``node_ids`` и ``doc_ids`` — объединение с сохранением порядка (сначала ``a``,
    затем новые из ``b``). ``subgraph`` из ``b`` побеждает, если задан / ``b``'s
    subgraph wins when set, otherwise ``a``'s is kept.
    """
    node_ids = _dedupe(a.node_ids + b.node_ids)
    doc_ids = _dedupe(a.doc_ids + b.doc_ids)
    subgraph = b.subgraph if b.subgraph is not None else a.subgraph
    return ChatAttachments(node_ids=node_ids, subgraph=subgraph, doc_ids=doc_ids)
