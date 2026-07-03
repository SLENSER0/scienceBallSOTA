"""Neo4j ``neo4j-admin import`` bulk-load CSV header/row generator (§22.6).

Turns plain node / edge dicts into the *typed-header* CSV that Neo4j's bulk importer
(``neo4j-admin database import``) consumes: a node file whose first line is a header
like ``id:ID,name,:LABEL`` (идентификатор, свойства, метка) followed by one aligned
data row per node, and a relationship file whose header is the fixed triple
``:START_ID,:END_ID,:TYPE`` (начало, конец, тип связи) followed by one row per edge.

Pure python — stdlib :mod:`csv` only. No graph/store access, no LLM, no clock: the
input dicts are the single source of truth and every output is deterministic for a
given input, so the produced CSV is hand-checkable.

Input shapes:

- node ``{"id": "m1", "label": "Material", "props": {"name": "Al", "hardness": 9.0}}``
  — ``props`` is optional; a missing property renders an empty cell in that node's row;
- edge ``{"start": "s", "end": "t", "type": "HAS"}``.

Column typing follows Neo4j's header syntax: the ``id:ID`` column comes first, then one
column per *first-seen* property (a ``float`` value tags the column ``:double``, an
``int`` → ``:long``, a ``bool`` → ``:boolean``, a ``str`` stays untyped/string), then
the ``:LABEL`` column last.

Entry points:

- :func:`node_columns` — the ordered node header column list;
- :func:`build_bundle` — assemble an :class:`ImportBundle` from nodes + edges;
- :func:`nodes_csv` / :func:`rels_csv` — render a bundle's node / relationship CSV text.

Kuzu note: custom node props are *not* queryable columns — a caller sourcing nodes from
a Kuzu store must ``RETURN`` base columns and hydrate the rest via ``get_node`` before
handing the assembled node dicts here (this module never touches a store itself).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Fixed reserved header columns (§22.6) — stable strings so renders are hand-checkable.
_ID_COLUMN = "id:ID"
_LABEL_COLUMN = ":LABEL"
_REL_HEADER: tuple[str, ...] = (":START_ID", ":END_ID", ":TYPE")

# CSV line terminator: ``\n`` (not the csv default ``\r\n``) so the first line equals the
# comma-joined header exactly and splitting on ``\n`` is unambiguous.
_LINE_TERMINATOR = "\n"


def _type_suffix(value: Any) -> str:
    """Return the Neo4j header type suffix for ``value`` (``""`` for string/default).

    Возвращает суффикс типа заголовка Neo4j. ``bool`` is checked before ``int`` because
    ``bool`` is a subclass of ``int`` in Python; strings and unknown types stay untyped
    (Neo4j treats an untyped property column as ``string``).
    """
    if isinstance(value, bool):
        return ":boolean"
    if isinstance(value, int):
        return ":long"
    if isinstance(value, float):
        return ":double"
    return ""


def _render_cell(value: Any) -> str:
    """Render a single property value as a CSV cell string.

    ``None`` → empty cell (пустая ячейка); ``bool`` → ``"true"``/``"false"`` (Neo4j
    boolean literal); everything else → ``str(value)``.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _node_props(node: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a node's property mapping (``props`` key, or empty)."""
    props = node.get("props")
    return props if isinstance(props, Mapping) else {}


@dataclass(frozen=True, slots=True)
class ImportBundle:
    """A fully-typed node + relationship CSV bundle for ``neo4j-admin import`` (§22.6).

    Immutable (неизменяемый) so a built bundle can be cached / shared safely.

    Fields:

    - ``node_header`` — the node file header columns (``id:ID`` … ``:LABEL``);
    - ``node_rows`` — one aligned data row per node (empty cell for a missing prop);
    - ``rel_header`` — the fixed ``(:START_ID, :END_ID, :TYPE)`` triple;
    - ``rel_rows`` — one ``(start, end, type)`` row per edge.
    """

    node_header: tuple[str, ...]
    node_rows: tuple[tuple[str, ...], ...]
    rel_header: tuple[str, ...]
    rel_rows: tuple[tuple[str, ...], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (§22.6 field order) for JSON / logging."""
        return {
            "node_header": list(self.node_header),
            "node_rows": [list(row) for row in self.node_rows],
            "rel_header": list(self.rel_header),
            "rel_rows": [list(row) for row in self.rel_rows],
        }


def node_columns(nodes: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the ordered node header columns: ``id:ID``, first-seen props, ``:LABEL``.

    Property columns are ordered by first appearance across ``nodes`` (свойства в порядке
    первого появления); each is tagged with the Neo4j type suffix inferred from its
    first-seen value (see :func:`_type_suffix`). The first column is always ``id:ID`` and
    the last is always ``:LABEL``, even when ``nodes`` is empty.
    """
    columns: list[str] = [_ID_COLUMN]
    seen: set[str] = set()
    for node in nodes:
        for name, value in _node_props(node).items():
            if name in seen:
                continue
            seen.add(name)
            columns.append(f"{name}{_type_suffix(value)}")
    columns.append(_LABEL_COLUMN)
    return columns


def _prop_names(header: Sequence[str]) -> list[str]:
    """Extract bare property names from a node header (drop ``id:ID`` / ``:LABEL``)."""
    # Property columns sit strictly between the fixed first (id:ID) and last (:LABEL).
    names: list[str] = []
    for column in header[1:-1]:
        name, _, _suffix = column.partition(":")
        names.append(name)
    return names


def build_bundle(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> ImportBundle:
    """Assemble an :class:`ImportBundle` from ``nodes`` and ``edges`` (§22.6).

    The node header is :func:`node_columns`; each node row aligns to it as
    ``(id, prop…, label)`` with an empty cell for any property the node lacks. Each edge
    row is ``(start, end, type)`` aligned to the fixed :data:`_REL_HEADER`.
    """
    node_header = node_columns(nodes)
    prop_names = _prop_names(node_header)

    node_rows: list[tuple[str, ...]] = []
    for node in nodes:
        props = _node_props(node)
        row = [_render_cell(node.get("id"))]
        row.extend(_render_cell(props[name]) if name in props else "" for name in prop_names)
        row.append(_render_cell(node.get("label")))
        node_rows.append(tuple(row))

    rel_rows: list[tuple[str, ...]] = []
    for edge in edges:
        rel_rows.append(
            (
                _render_cell(edge.get("start")),
                _render_cell(edge.get("end")),
                _render_cell(edge.get("type")),
            )
        )

    return ImportBundle(
        node_header=tuple(node_header),
        node_rows=tuple(node_rows),
        rel_header=_REL_HEADER,
        rel_rows=tuple(rel_rows),
    )


def _render_csv(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render ``header`` + ``rows`` as CSV text (header line first, ``\\n``-terminated).

    Uses :mod:`csv` for correct quoting/escaping; the first line always equals the
    comma-joined ``header`` (простые значения не требуют экранирования).
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=_LINE_TERMINATOR)
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(list(row))
    return buffer.getvalue()


def nodes_csv(bundle: ImportBundle) -> str:
    """Render ``bundle``'s node CSV: the header line then one line per node row.

    With no nodes the result is a single line — the comma-joined ``node_header``.
    """
    return _render_csv(bundle.node_header, bundle.node_rows)


def rels_csv(bundle: ImportBundle) -> str:
    """Render ``bundle``'s relationship CSV: ``:START_ID,:END_ID,:TYPE`` then edge rows."""
    return _render_csv(bundle.rel_header, bundle.rel_rows)
