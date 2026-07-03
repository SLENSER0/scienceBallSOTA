"""Trivial Graph Format (TGF) export (§22).

TGF is a minimal, human-readable graph interchange format understood by yEd,
graph-tool and other tools: a block of ``id label`` node lines, a single ``#``
separator line, then a block of ``src tgt label`` edge lines. This complements the
richer exporters (§11.15 JSON/Markdown, community export) with a *compact* dump that a
curator can eyeball or import into a diagramming tool.

Формат TGF (простой графовый формат): сначала узлы (``id label``), затем строка-
разделитель ``#``, затем рёбра (``src tgt label``). Метка узла — ``name`` или, если её
нет, сам ``id``; метка ребра — ``type`` или пустая строка (тогда ребро печатается как
``src tgt`` без завершающего пробела).

Pure python (stdlib only): no graph/store access, no LLM, no clock. The input dicts
are the single source of truth; rendering is deterministic for a given input.

Kuzu note: custom node props (name, type, …) are *not* queryable columns — a caller
reading nodes/edges from the store must ``RETURN`` base columns and hydrate the rest
via ``get_node`` before handing the dicts to :func:`build_tgf`.

Entry points:

- :func:`build_tgf` — assemble a :class:`TgfDoc` from node/edge dicts;
- :func:`to_tgf` — render a :class:`TgfDoc` to the TGF text form.
"""

from __future__ import annotations

from dataclasses import dataclass

# TGF separator between the node block and the edge block (§22): exactly one ``#`` on
# its own line, always present (even for an empty graph).
_SEP = "#"


def _flatten(text: str) -> str:
    """Flatten *text* to a single line: newlines (``\\n`` / ``\\r``) become spaces.

    Свести метку к одной строке — TGF is line-oriented, so an embedded newline would
    corrupt the node/edge block. Carriage returns are handled too, so ``\\r\\n`` does
    not leave a stray space-space pair beyond the single replacement per char.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")


@dataclass(frozen=True)
class TgfDoc:
    """A parsed TGF document (§22): node and edge tuples ready to render.

    ``nodes`` is a tuple of ``(id, label)`` pairs; ``edges`` is a tuple of
    ``(src, tgt, label)`` triples (label may be the empty string). Frozen so a built
    document is an immutable value; :meth:`as_dict` gives a JSON-friendly view.
    """

    nodes: tuple[tuple[str, str], ...]
    edges: tuple[tuple[str, str, str], ...]

    def as_dict(self) -> dict[str, list[tuple[str, ...]]]:
        """Return a JSON-friendly mapping ``{"nodes": [...], "edges": [...]}`` (§22).

        ``nodes`` is a list of 2-tuples, ``edges`` a list of 3-tuples, preserving order.
        """
        return {
            "nodes": [tuple(n) for n in self.nodes],
            "edges": [tuple(e) for e in self.edges],
        }


def build_tgf(nodes: list[dict], edges: list[dict]) -> TgfDoc:
    """Build a :class:`TgfDoc` from node and edge dicts (§22).

    Node label = ``name`` if present and truthy, else the ``id`` (метка узла — имя или
    сам идентификатор). Edge label = ``type`` if present, else the empty string. Ids /
    endpoints are read from ``id`` for nodes and ``source`` / ``target`` for edges and
    stringified; every label is flattened to a single line (see :func:`_flatten`).
    """
    built_nodes: list[tuple[str, str]] = []
    for node in nodes:
        node_id = str(node["id"])
        name = node.get("name")
        label = str(name) if name else node_id
        built_nodes.append((node_id, _flatten(label)))

    built_edges: list[tuple[str, str, str]] = []
    for edge in edges:
        src = str(edge["source"])
        tgt = str(edge["target"])
        label = _flatten(str(edge.get("type") or ""))
        built_edges.append((src, tgt, label))

    return TgfDoc(nodes=tuple(built_nodes), edges=tuple(built_edges))


def to_tgf(doc: TgfDoc) -> str:
    """Render *doc* to TGF text (§22).

    Layout: each node as ``id label`` (one per line), then a line that is exactly ``#``,
    then each edge as ``src tgt label`` (or ``src tgt`` with no trailing space when the
    edge label is empty). An empty graph renders as just ``#``. Lines are joined with
    ``\\n`` and there is no trailing newline, so the output is deterministic and
    hand-checkable.
    """
    lines: list[str] = [f"{node_id} {label}" for node_id, label in doc.nodes]
    lines.append(_SEP)
    for src, tgt, label in doc.edges:
        lines.append(f"{src} {tgt} {label}" if label else f"{src} {tgt}")
    return "\n".join(lines)
