"""RDF N-Quads export of knowledge-graph edges into per-source named graphs (§22.6).

Экспорт рёбер графа знаний в стандартную W3C-сериализацию N-Quads: по одному
*квадру* на строку (``subject predicate object graph .``). В отличие от
одно-графового N-Triples/Turtle-экспортёра (:mod:`kg_retrievers.graph_rdf_ntriples`),
каждый квад помещается в *именованный граф* своего источника, поэтому провенанс
(из какого документа пришло ребро) сохраняется прямо в сериализации.

Чистый python (только stdlib): без доступа к графу/хранилищу, без LLM, без
часов — на входе обычные dict-рёбра, на выходе детерминированный текст.

The mapping is fixed (§22.6) and reuses the N-Triples base/ontology IRIs:

- subject/object are entity IRIs under ``https://science-ball.example/kg/m/{id}``;
- the predicate is the edge ``type`` in the ``ontology#`` namespace;
- the *graph label* is a per-source IRI minted from the edge's ``source_doc`` (or
  ``graph``) under ``https://science-ball.example/kg/graph/{source}``; edges with no
  such field fall back to a caller-supplied ``default_graph`` (``urn:kg:default``).

Entry points:

- :class:`RdfQuad` — a frozen quad ``(subject, predicate, object_, is_literal, graph)``
  with :meth:`~RdfQuad.as_dict` and :meth:`~RdfQuad.to_nquad`;
- :func:`edge_quad` — the single named-graph quad of an edge;
- :func:`to_nquads` — an N-Quads document (one quad per ``\\n``-terminated line).

Kuzu note: custom node/edge props (source_doc, …) are *not* queryable columns — a
caller reading edges from the store must ``RETURN`` base columns and hydrate the
rest via ``get_node`` before handing the dicts here; tests build a plain dict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_rdf_ntriples import (
    BASE_IRI,
    entity_iri,
    ontology_iri,
)

# §22.6 fixed IRIs — the per-source named-graph namespace, reusing the fixed base.
GRAPH_NS = f"{BASE_IRI}graph/"
DEFAULT_GRAPH = "urn:kg:default"


def _escape_literal(value: str) -> str:
    """Escape a string for an N-Quads literal body (§22.6, W3C escaping).

    Backslash and double-quote are backslash-escaped, and tab / newline / carriage
    return use their canonical ``\\t`` / ``\\n`` / ``\\r`` escapes so a quad stays on
    one physical line.
    """
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    return out.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def graph_iri(source: str) -> str:
    """Named-graph IRI for a source: ``…/kg/graph/{source}`` (§22.6)."""
    return f"{GRAPH_NS}{source}"


@dataclass(frozen=True)
class RdfQuad:
    """A single RDF quad — a triple plus a named-graph label (§22.6).

    ``subject``/``predicate`` are bare IRI strings (no angle brackets); ``object_`` is
    either a bare IRI (``is_literal=False``) or the *raw* literal text (``is_literal``
    true). ``graph`` is the bare IRI of the named graph. :meth:`to_nquad` handles all
    angle-wrapping and escaping, so the dataclass stays free of serialization syntax.
    """

    subject: str
    predicate: str
    object_: str
    is_literal: bool
    graph: str

    def as_dict(self) -> dict[str, Any]:
        """§22.6 mapping of the quad, in fixed key order."""
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object_,
            "is_literal": self.is_literal,
            "graph": self.graph,
        }

    def to_nquad(self) -> str:
        """Render as one N-Quads statement, terminated by ``' .'`` (§22.6).

        Subject, predicate and graph are always angle-bracket-wrapped IRIs. The object
        is a quoted, backslash-escaped literal when ``is_literal`` is true, else an
        angle-wrapped IRI. The line has four whitespace-separated terms before the dot
        and no trailing newline.
        """
        subj = f"<{self.subject}>"
        pred = f"<{self.predicate}>"
        obj = f'"{_escape_literal(self.object_)}"' if self.is_literal else f"<{self.object_}>"
        graph = f"<{self.graph}>"
        return f"{subj} {pred} {obj} {graph} ."


def edge_quad(edge: dict[str, Any], default_graph: str = DEFAULT_GRAPH) -> RdfQuad:
    """One named-graph quad for an edge ``src -[type]-> dst`` (§22.6).

    ``edge`` must carry ``source``/``target`` (aliases ``src``/``dst``/``from``/``to``
    accepted) and a ``type``; the predicate is the ontology IRI of that type and both
    subject and object are entity IRIs. The graph label is minted from ``source_doc``
    (or ``graph``) via :func:`graph_iri`; when neither is present the quad is placed in
    ``default_graph`` verbatim (its own IRI, not run through :func:`graph_iri`).
    """
    source = edge.get("source", edge.get("src", edge.get("from")))
    target = edge.get("target", edge.get("dst", edge.get("to")))
    rel_type = edge["type"]
    source_doc = edge.get("source_doc", edge.get("graph"))
    graph = graph_iri(str(source_doc)) if source_doc else default_graph
    return RdfQuad(
        subject=entity_iri(str(source)),
        predicate=ontology_iri(str(rel_type)),
        object_=entity_iri(str(target)),
        is_literal=False,
        graph=graph,
    )


def to_nquads(edges: Sequence[dict[str, Any]]) -> str:
    """Serialize edges as a W3C N-Quads document (§22.6).

    One quad per line, each terminated by ``' .'`` and a newline; the line count equals
    the number of edges. Empty input yields the empty string (no trailing newline).
    """
    if not edges:
        return ""
    return "".join(f"{edge_quad(edge).to_nquad()}\n" for edge in edges)
