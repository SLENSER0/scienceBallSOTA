"""§22.6 — GML (Graph Modeling Language) export for knowledge-graph subgraphs.

Чистый сериализатор (pure serializer): turns plain node/edge dicts into a GML
document — the classic ``graph [ node [ ... ] edge [ ... ] ]`` text read by
Gephi, yEd and :func:`networkx.read_gml`. This is *distinct* from the sibling
GraphML (XML) exporter: GML is a compact, brace-delimited key/value grammar, not
XML. Pure stdlib, no graph store, no I/O, no LLM, no clock — dicts in, text out —
so every render is deterministic and hand-checkable.

Модель (model): integer ids are assigned 0-based in *input order*; edges reference
their endpoints by the node ``id`` string, resolved back to that integer. Each node
renders one ``node [ id <int> label "<name>" ]`` block; the label is drawn from
``name`` (falling back to ``label`` then ``type`` then the id string). Each edge
renders one ``edge [ source <int> target <int> label "<rel>" ]`` block, labelled by
its relation (``rel`` then ``type``). :func:`_escape_gml` doubles embedded double
quotes so an arbitrary name cannot break the quoted-string grammar.

Entry points:

- :class:`GmlGraph` — frozen result: ``directed`` flag plus ordered ``nodes`` /
  ``edges`` tuples, with :meth:`GmlGraph.as_dict`;
- :func:`to_gml` — build a node/edge dict pair into the GML document string;
- :func:`_escape_gml` — double internal double quotes for the GML string grammar.

Kuzu note: custom node props are *not* queryable columns — a caller reading nodes
from the store must ``RETURN`` base columns and hydrate the rest via ``get_node``
before handing the canonical dicts here (tests build dicts in memory, never query
custom props).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_INDENT = "  "

# Node fields tried, in order, for the display label (RU: поля для метки узла).
_LABEL_KEYS = ("name", "label", "type")
# Edge fields tried, in order, for the relation label (RU: поля для метки ребра).
_REL_KEYS = ("rel", "type", "label")


def _escape_gml(s: str) -> str:
    """Double internal double quotes for a GML quoted string (RU: экранирование).

    GML string values are wrapped in double quotes; the grammar has no backslash
    escape, so an embedded ``"`` is represented by doubling it (``""``).
    """
    return s.replace('"', '""')


def _pick(d: dict[str, Any], keys: Sequence[str], default: str) -> str:
    """Return the first present, non-empty value among *keys* (RU: первое поле)."""
    for key in keys:
        value = d.get(key)
        if value is not None and value != "":
            return str(value)
    return default


@dataclass(frozen=True)
class GmlGraph:
    """§22.6 — frozen GML model: directed flag plus node / edge tuples.

    ``directed`` — ``1``/``0`` GML flag; ``nodes`` — tuple of ``(int_id, id_str,
    label)``; ``edges`` — tuple of ``(source_int, target_int, rel)``. RU: замороженная
    модель графа для сериализации в GML.
    """

    directed: int
    nodes: tuple[tuple[int, str, str], ...]
    edges: tuple[tuple[int, int, str], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view (RU: словарь) for logging / JSON."""
        return {
            "directed": self.directed,
            "nodes": [list(node) for node in self.nodes],
            "edges": [list(edge) for edge in self.edges],
        }

    def render(self) -> str:
        """Serialize this model to a GML document string (RU: сериализация)."""
        lines = ["graph [", f"{_INDENT}directed {self.directed}"]
        for int_id, _id_str, label in self.nodes:
            lines.append(f"{_INDENT}node [")
            lines.append(f"{_INDENT * 2}id {int_id}")
            lines.append(f'{_INDENT * 2}label "{_escape_gml(label)}"')
            lines.append(f"{_INDENT}]")
        for source_int, target_int, rel in self.edges:
            lines.append(f"{_INDENT}edge [")
            lines.append(f"{_INDENT * 2}source {source_int}")
            lines.append(f"{_INDENT * 2}target {target_int}")
            lines.append(f'{_INDENT * 2}label "{_escape_gml(rel)}"')
            lines.append(f"{_INDENT}]")
        lines.append("]")
        return "\n".join(lines) + "\n"


def _build(nodes: Sequence[dict], edges: Sequence[dict], directed: bool) -> GmlGraph:
    """Assemble a :class:`GmlGraph` from raw dicts (RU: сборка модели)."""
    node_tuples: list[tuple[int, str, str]] = []
    id_to_int: dict[str, int] = {}
    for int_id, node in enumerate(nodes):
        id_str = str(node.get("id", int_id))
        label = _pick(node, _LABEL_KEYS, id_str)
        node_tuples.append((int_id, id_str, label))
        id_to_int.setdefault(id_str, int_id)

    edge_tuples: list[tuple[int, int, str]] = []
    for edge in edges:
        source = id_to_int.get(str(edge.get("source")), -1)
        target = id_to_int.get(str(edge.get("target")), -1)
        rel = _pick(edge, _REL_KEYS, "")
        edge_tuples.append((source, target, rel))

    return GmlGraph(
        directed=1 if directed else 0,
        nodes=tuple(node_tuples),
        edges=tuple(edge_tuples),
    )


def to_gml(nodes: Sequence[dict], edges: Sequence[dict], directed: bool = True) -> str:
    """Serialize node/edge dicts to a GML document (RU: сериализация в GML).

    Integer ids are assigned 0-based in input order; edges resolve their
    ``source``/``target`` id strings to those integers. ``directed`` toggles the
    GML ``directed 1``/``directed 0`` flag.
    """
    return _build(nodes, edges, directed).render()
