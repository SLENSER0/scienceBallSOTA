"""Дельта графа для ``POST /graph/diff`` (§14.6).

Помощник для эндпоинта ``POST /graph/diff`` (§14.6): раньше не было
переиспользуемой функции для сравнения двух снимков графа. Модуль на чистом
stdlib принимает форму ``{'nodes':[...],'edges':[...]}`` до и после изменения
и вычисляет трёхстороннюю дельту (добавлено/удалено/изменено) по ключу узла и
ребра. Узел/ребро считается «изменённым», когда ключ совпадает, но хотя бы одно
другое поле отличается; такая запись несёт снимки ``_before`` / ``_after``.

Graph delta helper for the §14.6 ``POST /graph/diff`` endpoint: no reusable
comparator existed for two ``{'nodes':[...],'edges':[...]}`` snapshots. Pure
stdlib — computes a three-way delta (added / removed / changed) keyed by node
and edge id. An item is ``changed`` when the key matches but any other field
differs; each changed entry carries ``_before`` / ``_after`` snapshots.

* :class:`GraphDiff` — неизменяемая дельта с :meth:`as_dict`.
* :func:`diff_graphs` — сравнение снимков ``before`` / ``after``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GraphDiff:
    """Неизменяемая дельта графа до/после (§14.6).

    Immutable before/after graph delta. Each of the six lists holds plain dicts;
    ``changed_*`` entries additionally carry ``_before`` / ``_after`` snapshots
    of the two matched records. :meth:`as_dict` yields the wire form plus derived
    counts ``{added, removed, changed}`` aggregated over nodes and edges.
    """

    added_nodes: list[dict[str, Any]]
    removed_nodes: list[dict[str, Any]]
    changed_nodes: list[dict[str, Any]]
    added_edges: list[dict[str, Any]]
    removed_edges: list[dict[str, Any]]
    changed_edges: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Структурное представление дельты + счётчики / wire form (§14.6).

        Returns exactly the six list keys plus derived integer counts. ``added``,
        ``removed`` and ``changed`` sum the corresponding node and edge lists.
        """
        added = len(self.added_nodes) + len(self.added_edges)
        removed = len(self.removed_nodes) + len(self.removed_edges)
        changed = len(self.changed_nodes) + len(self.changed_edges)
        return {
            "added_nodes": list(self.added_nodes),
            "removed_nodes": list(self.removed_nodes),
            "changed_nodes": list(self.changed_nodes),
            "added_edges": list(self.added_edges),
            "removed_edges": list(self.removed_edges),
            "changed_edges": list(self.changed_edges),
            "added": added,
            "removed": removed,
            "changed": changed,
        }


def _index(items: Sequence[Mapping[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    """Проиндексировать записи по ключу / index records by ``key`` (§14.6).

    Records without the key are skipped. On a duplicate key the last record wins,
    matching last-write semantics of a keyed store.
    """
    out: dict[Any, dict[str, Any]] = {}
    for item in items:
        if key in item:
            out[item[key]] = dict(item)
    return out


def _split(
    before: Mapping[Any, dict[str, Any]],
    after: Mapping[Any, dict[str, Any]],
    key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Трёхсторонний раскол по ключу / three-way split by key (§14.6).

    Returns ``(added, removed, changed)`` where ``added`` ids exist only in
    ``after``, ``removed`` only in ``before``, and ``changed`` share the id but
    differ in any other field. Order follows ``after`` (then ``before`` leftovers
    for removals) so keyed, non-positional matching holds under reordering.
    """
    added: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for item_key, rec in after.items():
        if item_key not in before:
            added.append(rec)
            continue
        prev = before[item_key]
        if prev != rec:
            entry: dict[str, Any] = {key: item_key}
            for field, value in rec.items():
                if field != key:
                    entry[field] = value
            entry["_before"] = dict(prev)
            entry["_after"] = dict(rec)
            changed.append(entry)
    removed = [rec for item_key, rec in before.items() if item_key not in after]
    return added, removed, changed


def diff_graphs(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    node_key: str = "id",
    edge_key: str = "id",
) -> GraphDiff:
    """Сравнить два снимка графа и вернуть дельту (§14.6).

    Compare two ``{'nodes':[...],'edges':[...]}`` snapshots and return a
    :class:`GraphDiff`. Missing ``nodes`` / ``edges`` keys are treated as empty.
    Nodes are keyed by ``node_key`` and edges by ``edge_key``; a byte-identical
    record appears in none of the added/removed/changed lists.

    :param before: снимок графа до изменения / graph snapshot before the change.
    :param after: снимок графа после изменения / graph snapshot after the change.
    :param node_key: имя ключевого поля узла / node key field name.
    :param edge_key: имя ключевого поля ребра / edge key field name.
    """
    before_nodes = _index(before.get("nodes", ()), node_key)
    after_nodes = _index(after.get("nodes", ()), node_key)
    before_edges = _index(before.get("edges", ()), edge_key)
    after_edges = _index(after.get("edges", ()), edge_key)

    added_n, removed_n, changed_n = _split(before_nodes, after_nodes, node_key)
    added_e, removed_e, changed_e = _split(before_edges, after_edges, edge_key)

    return GraphDiff(
        added_nodes=added_n,
        removed_nodes=removed_n,
        changed_nodes=changed_n,
        added_edges=added_e,
        removed_edges=removed_e,
        changed_edges=changed_e,
    )
