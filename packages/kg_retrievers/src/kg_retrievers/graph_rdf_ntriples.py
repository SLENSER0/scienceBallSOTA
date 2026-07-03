"""RDF N-Triples / Turtle export of the knowledge graph (§22.6).

Экспорт графа знаний в стандартные RDF-сериализации W3C: N-Triples (по одной
тройке на строку) и Turtle (документ с ``@prefix``-заголовком). Чистый python
(только stdlib): без доступа к графу/хранилищу, без LLM, без часов — на входе
обычные dict-узлы и dict-рёбра, на выходе детерминированный текст.

The mapping from graph rows to RDF is fixed (§22.6):

- entity IRIs are minted under a fixed base IRI ``https://science-ball.example/kg/``
  in the ``m/`` namespace (``<https://science-ball.example/kg/m/{id}>``);
- a node's ``label`` becomes an ``rdf:type`` statement whose object is an ontology
  IRI ``<https://science-ball.example/kg/ontology#{Label}>``;
- a node's ``name`` becomes an ``rdfs:label`` statement whose object is a *string
  literal* (``"..."``, quoted and backslash-escaped);
- an edge's ``type`` becomes a predicate IRI in the same ``ontology#`` namespace,
  linking the source and target entity IRIs.

Entry points:

- :class:`RdfTriple` — a frozen triple ``(subject, predicate, object_, is_literal)``
  with :meth:`~RdfTriple.as_dict` and :meth:`~RdfTriple.to_ntriple`;
- :func:`node_triples` — the ``rdf:type`` (+ optional ``rdfs:label``) triples of a node;
- :func:`edge_triple` — the single predicate triple of an edge;
- :func:`to_ntriples` — an N-Triples document (one triple per ``\\n``-terminated line);
- :func:`to_turtle` — a Turtle document with ``@prefix`` header.

Kuzu note: custom node props (name, …) are *not* queryable columns — a caller
reading nodes from the store must ``RETURN`` base columns and hydrate the rest via
``get_node`` before handing the dicts here; tests build a plain in-memory dict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# §22.6 fixed IRIs — stable strings so renders are hand-checkable.
BASE_IRI = "https://science-ball.example/kg/"
ENTITY_NS = f"{BASE_IRI}m/"
ONTOLOGY_NS = f"{BASE_IRI}ontology#"
RDF_TYPE_IRI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL_IRI = "http://www.w3.org/2000/01/rdf-schema#label"

# Turtle @prefix bindings (§22.6) — order is fixed for deterministic output.
_TURTLE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
    ("m", ENTITY_NS),
    ("onto", ONTOLOGY_NS),
)


def entity_iri(node_id: str) -> str:
    """IRI сущности: ``https://science-ball.example/kg/m/{node_id}`` (§22.6)."""
    return f"{ENTITY_NS}{node_id}"


def ontology_iri(name: str) -> str:
    """Ontology-term IRI: ``https://science-ball.example/kg/ontology#{name}`` (§22.6)."""
    return f"{ONTOLOGY_NS}{name}"


def _escape_literal(value: str) -> str:
    """Escape a string for an N-Triples literal body (§22.6, W3C escaping).

    Backslash and double-quote are backslash-escaped, and the C0 control characters
    tab / newline / carriage-return use their canonical ``\\t`` / ``\\n`` / ``\\r``
    escapes, so :meth:`RdfTriple.to_ntriple` stays one triple per single line.
    """
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    return out.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


@dataclass(frozen=True)
class RdfTriple:
    """A single RDF statement (§22.6).

    ``subject`` and ``predicate`` are bare IRI strings (no angle brackets); ``object_``
    is either a bare IRI (``is_literal=False``) or the *raw* text of a string literal
    (``is_literal=True``). :meth:`to_ntriple` handles wrapping and escaping so the
    dataclass itself stays free of serialization syntax.
    """

    subject: str
    predicate: str
    object_: str
    is_literal: bool

    def as_dict(self) -> dict[str, Any]:
        """§22.6 mapping of the triple, in fixed key order."""
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object_,
            "is_literal": self.is_literal,
        }

    def to_ntriple(self) -> str:
        """Render as one N-Triples statement, terminated by ``' .'`` (§22.6).

        Subject and predicate are always angle-bracket-wrapped IRIs. The object is a
        quoted, backslash-escaped string literal when ``is_literal`` is true, else an
        angle-bracket-wrapped IRI. The returned line has no trailing newline.
        """
        subj = f"<{self.subject}>"
        pred = f"<{self.predicate}>"
        obj = f'"{_escape_literal(self.object_)}"' if self.is_literal else f"<{self.object_}>"
        return f"{subj} {pred} {obj} ."


def node_triples(node: dict[str, Any]) -> list[RdfTriple]:
    """Triples for one node: an ``rdf:type`` plus an optional ``rdfs:label`` (§22.6).

    ``node`` must carry an ``id``; its ``label`` (if present) yields an ``rdf:type``
    statement to the ontology IRI, and its ``name`` (if present and non-empty) yields
    an ``rdfs:label`` string literal. Order is type-then-label, deterministically.
    """
    node_id = str(node["id"])
    subject = entity_iri(node_id)
    triples: list[RdfTriple] = []
    label = node.get("label")
    if label:
        triples.append(
            RdfTriple(
                subject=subject,
                predicate=RDF_TYPE_IRI,
                object_=ontology_iri(str(label)),
                is_literal=False,
            )
        )
    name = node.get("name")
    if name:
        triples.append(
            RdfTriple(
                subject=subject,
                predicate=RDFS_LABEL_IRI,
                object_=str(name),
                is_literal=True,
            )
        )
    return triples


def edge_triple(edge: dict[str, Any]) -> RdfTriple:
    """One triple for an edge ``src -[type]-> dst`` (§22.6).

    ``edge`` must carry ``source``/``target`` (aliases ``src``/``dst``/``from``/``to``
    are accepted) and a ``type``; the predicate is the ontology IRI of that type, and
    both object and subject are entity IRIs.
    """
    source = edge.get("source", edge.get("src", edge.get("from")))
    target = edge.get("target", edge.get("dst", edge.get("to")))
    rel_type = edge["type"]
    return RdfTriple(
        subject=entity_iri(str(source)),
        predicate=ontology_iri(str(rel_type)),
        object_=entity_iri(str(target)),
        is_literal=False,
    )


def all_triples(
    nodes: Sequence[dict[str, Any]], edges: Sequence[dict[str, Any]]
) -> list[RdfTriple]:
    """Every triple for ``nodes`` then ``edges``, in input order (§22.6)."""
    triples: list[RdfTriple] = []
    for node in nodes:
        triples.extend(node_triples(node))
    for edge in edges:
        triples.append(edge_triple(edge))
    return triples


def to_ntriples(nodes: Sequence[dict[str, Any]], edges: Sequence[dict[str, Any]]) -> str:
    """Serialize the graph as a W3C N-Triples document (§22.6).

    One triple per line, each line terminated by ``' .'`` and a newline; the line
    count equals the total number of triples. Empty input yields the empty string
    (no trailing newline).
    """
    triples = all_triples(nodes, edges)
    if not triples:
        return ""
    return "".join(f"{t.to_ntriple()}\n" for t in triples)


def to_turtle(nodes: Sequence[dict[str, Any]], edges: Sequence[dict[str, Any]]) -> str:
    """Serialize the graph as a Turtle document with ``@prefix`` header (§22.6).

    The header binds ``rdf``, ``rdfs``, ``m`` and ``onto`` prefixes; the body reuses
    the N-Triples statements verbatim (a valid Turtle subset), so the document is
    deterministic and hand-checkable. Empty input still emits the prefix header.
    """
    header = "".join(f"@prefix {name}: <{iri}> .\n" for name, iri in _TURTLE_PREFIXES)
    body = to_ntriples(nodes, edges)
    if not body:
        return header
    return f"{header}\n{body}"
