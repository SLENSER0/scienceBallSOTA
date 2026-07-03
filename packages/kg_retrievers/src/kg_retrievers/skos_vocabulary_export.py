"""SKOS concept-scheme export of a KG taxonomy (§22).

Экспорт таксономии графа знаний (словарь материалов/свойств/режимов) в SKOS
``ConceptScheme`` в сериализации Turtle — для загрузки в онтологические
инструменты и реестры словарей. В отличие от модулей ``graph_rdf_ntriples`` /
``graph_rdf_nquads``, которые эмитят простые тройки type/label, здесь строится
структура SKOS: ``skos:broader``/``skos:narrower``-иерархия, ``skos:prefLabel`` и
``skos:altLabel``. Чистый python (только stdlib): без доступа к графу/хранилищу,
без LLM, без часов — на входе обычные dict-термины, на выходе детерминированный
текст.

The mapping from taxonomy terms to SKOS is fixed (§22):

- each term becomes a ``skos:Concept`` under the empty ``:`` namespace
  (``:{concept_id}``) and is tied to the scheme via ``skos:inScheme``;
- a term's label becomes a ``skos:prefLabel`` language-tagged literal (``"..."@en``);
- a term's parent(s) become ``skos:broader`` object references to sibling concepts
  (a root term — one without parents — emits no ``skos:broader``);
- a term's aliases become ``skos:altLabel`` language-tagged literals, one per alias.

Entry points:

- :class:`SkosConcept` — a frozen concept ``(concept_id, pref_label, broader,
  alt_labels)`` with :meth:`~SkosConcept.as_dict`;
- :func:`build_concepts` — map loosely-keyed term dicts to concepts;
- :func:`to_turtle` — a Turtle document with SKOS ``@prefix`` header, one
  ``skos:ConceptScheme`` and one block per concept.

Kuzu note: custom node props (label, aliases, …) are *not* queryable columns — a
caller reading taxonomy nodes from the store must ``RETURN`` base columns and
hydrate the rest via ``get_node`` before handing the dicts here; tests build a
plain in-memory list of dicts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# §22 SKOS / RDF namespaces — stable strings so renders are hand-checkable.
SKOS_NS = "http://www.w3.org/2004/02/skos/core#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
VOCAB_NS = "https://science-ball.example/kg/vocab#"

# Turtle @prefix bindings (§22) — order is fixed for deterministic output.
_TURTLE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("skos", SKOS_NS),
    ("rdf", RDF_NS),
    ("", VOCAB_NS),
)

# Term-dict key aliases accepted by :func:`build_concepts` (§22).
_ID_KEYS = ("id", "concept_id", "term_id")
_LABEL_KEYS = ("pref_label", "label", "name", "prefLabel")
_PARENT_KEYS = ("parents", "parent", "broader")
_ALIAS_KEYS = ("alt_labels", "aliases", "altLabels", "synonyms")


def _escape_literal(value: str) -> str:
    """Escape a string for a Turtle literal body (§22, W3C escaping).

    Backslash and double-quote are backslash-escaped, and tab / newline / carriage
    return use their canonical ``\\t`` / ``\\n`` / ``\\r`` escapes so each concept
    block stays syntactically valid Turtle.
    """
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    return out.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def _first_present(term: dict[str, Any], keys: Sequence[str]) -> Any:
    """Return ``term[k]`` for the first ``k`` in ``keys`` present with a value."""
    for key in keys:
        if key in term and term[key] not in (None, ""):
            return term[key]
    return None


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce a scalar / iterable ``value`` into a tuple of non-empty strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    items = tuple(str(v) for v in value if v not in (None, ""))
    return items


@dataclass(frozen=True)
class SkosConcept:
    """A single SKOS concept in the exported scheme (§22).

    ``concept_id`` is the bare local name rendered as ``:{concept_id}``; ``pref_label``
    is the preferred label text (rendered ``"..."@en``); ``broader`` is a tuple of
    parent concept ids (each a ``skos:broader`` reference, empty for a root); and
    ``alt_labels`` is a tuple of alternative-label texts (each a ``skos:altLabel``).
    """

    concept_id: str
    pref_label: str
    broader: tuple[str, ...]
    alt_labels: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """§22 mapping of the concept, in fixed key order (``broader`` stays a tuple)."""
        return {
            "concept_id": self.concept_id,
            "pref_label": self.pref_label,
            "broader": self.broader,
            "alt_labels": self.alt_labels,
        }


def build_concepts(terms: list[dict]) -> tuple[SkosConcept, ...]:
    """Map loosely-keyed taxonomy ``terms`` to SKOS concepts (§22).

    Each term must carry an id (``id`` / ``concept_id`` / ``term_id``) and a label
    (``pref_label`` / ``label`` / ``name``). Parents come from ``parents`` /
    ``parent`` / ``broader`` (a scalar or an iterable) and become ``skos:broader``;
    aliases come from ``alt_labels`` / ``aliases`` / ``synonyms`` and become
    ``skos:altLabel``. Input order is preserved.
    """
    concepts: list[SkosConcept] = []
    for term in terms:
        raw_id = _first_present(term, _ID_KEYS)
        if raw_id is None:
            raise ValueError("taxonomy term is missing an id key")
        label = _first_present(term, _LABEL_KEYS)
        concepts.append(
            SkosConcept(
                concept_id=str(raw_id),
                pref_label="" if label is None else str(label),
                broader=_as_str_tuple(_first_present(term, _PARENT_KEYS)),
                alt_labels=_as_str_tuple(_first_present(term, _ALIAS_KEYS)),
            )
        )
    return tuple(concepts)


def _concept_block(concept: SkosConcept, *, scheme_id: str) -> str:
    """Render one concept as a semicolon-separated Turtle block (§22).

    The predicate order is fixed: ``a skos:Concept`` → ``skos:inScheme`` →
    ``skos:prefLabel`` → each ``skos:broader`` → each ``skos:altLabel``. The block is
    terminated by a full stop.
    """
    lines: list[str] = [f":{concept.concept_id} a skos:Concept"]
    lines.append(f"skos:inScheme :{scheme_id}")
    lines.append(f'skos:prefLabel "{_escape_literal(concept.pref_label)}"@en')
    for parent in concept.broader:
        lines.append(f"skos:broader :{parent}")
    for alias in concept.alt_labels:
        lines.append(f'skos:altLabel "{_escape_literal(alias)}"@en')
    body = " ;\n    ".join(lines)
    return f"{body} .\n"


def to_turtle(concepts: Sequence[SkosConcept], *, scheme_id: str = "vocab") -> str:
    """Serialize ``concepts`` as a SKOS ``ConceptScheme`` in Turtle (§22).

    The header binds the ``skos``, ``rdf`` and empty (``:``) prefixes; one
    ``:{scheme_id} a skos:ConceptScheme`` line declares the scheme; then one block
    per concept follows in input order. Empty input still emits the header and the
    scheme declaration, so the document is always a well-formed concept scheme.
    """
    header = "".join(f"@prefix {name}: <{iri}> .\n" for name, iri in _TURTLE_PREFIXES)
    scheme = f":{scheme_id} a skos:ConceptScheme .\n"
    blocks = "".join(_concept_block(c, scheme_id=scheme_id) for c in concepts)
    if not blocks:
        return f"{header}\n{scheme}"
    return f"{header}\n{scheme}\n{blocks}"
