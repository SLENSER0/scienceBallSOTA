"""Domain-glossary builder over the graph (§24.20 / §3.12).

§3.12 packs every entity's surface forms (name + canonical_name + pipe-separated
``aliases_text``, RU|EN) onto the node, and the ``entity_name_index`` (§8.4) is built
``FOR (n:Material|Property|Equipment|... ) ON EACH [n.name, n.canonical_name,
n.aliases_text]``. This module turns that same surface material into a *glossary*
(глоссарий) — a flat, bilingual list of canonical terms that experts can browse,
search and correct in the §24.20 expert-edit UI.

For each :Material / :Property / :Equipment / :Method node it emits a frozen
:class:`GlossaryTerm` with the Russian and English canonical forms, the de-duplicated
alias list and an optional definition. Callers may narrow the list by a substring
query ``q`` (matched against RU/EN forms and aliases) and/or a node ``type``.

Kuzu note (§3 / ADR-0005): custom node properties (``canonical_ru`` / ``canonical_en``
/ ``definition``) are *not* queryable columns — they live in the ``props`` JSON blob.
So the Cypher MATCH RETURNs only base columns (here: ``id``) and every other field is
read back through :meth:`~kg_retrievers.graph_store.KuzuGraphStore.get_node`, which
merges the ``props`` JSON into the node dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import NodeLabel

_log = get_logger("glossary_builder")

# The node labels that make up the domain glossary (§24.20). ``Method`` maps to a
# glossary term / classification (§10.6); Material/Property/Equipment are the core
# resolvable entities carrying names + aliases (§3.12).
GLOSSARY_LABELS: tuple[str, ...] = (
    str(NodeLabel.MATERIAL),
    str(NodeLabel.PROPERTY),
    str(NodeLabel.EQUIPMENT),
    str(NodeLabel.METHOD),
)

# Canonical-form fallbacks, most-specific first. The dedicated ``canonical_ru`` /
# ``canonical_en`` props win; otherwise we fall back to the base surface columns so a
# term is never left without a display form (§3.12 name / canonical_name).
_RU_FIELDS: tuple[str, ...] = ("canonical_ru", "name_ru", "name", "canonical_name")
_EN_FIELDS: tuple[str, ...] = ("canonical_en", "name_en", "canonical_name", "name")

_ALIAS_SEP = "|"


@dataclass(frozen=True)
class GlossaryTerm:
    """One canonical glossary entry — bilingual, with aliases (§24.20 / §3.12)."""

    id: str
    type: str
    canonical_ru: str
    canonical_en: str
    aliases: tuple[str, ...]
    definition: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "canonical_ru": self.canonical_ru,
            "canonical_en": self.canonical_en,
            "aliases": list(self.aliases),
            "definition": self.definition,
        }


def _first(node: dict[str, Any], fields: tuple[str, ...]) -> str:
    """First non-empty value among ``fields`` (стрип), else ``""``."""
    for key in fields:
        val = node.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _aliases(node: dict[str, Any]) -> tuple[str, ...]:
    """De-duplicated alias list from ``aliases_text`` (|-split) + any ``aliases`` prop."""
    out: list[str] = []
    text = node.get("aliases_text")
    if text:
        out.extend(part.strip() for part in str(text).split(_ALIAS_SEP) if part.strip())
    extra = node.get("aliases")
    if isinstance(extra, (list, tuple)):
        out.extend(str(a).strip() for a in extra if str(a).strip())
    elif isinstance(extra, str) and extra.strip():
        out.extend(part.strip() for part in extra.split(_ALIAS_SEP) if part.strip())
    return tuple(dict.fromkeys(out))  # order-preserving de-dup


def _term_from_node(node: dict[str, Any]) -> GlossaryTerm:
    """Assemble one :class:`GlossaryTerm` from a full node dict (base cols + props)."""
    return GlossaryTerm(
        id=str(node["id"]),
        type=str(node.get("label", "")),
        canonical_ru=_first(node, _RU_FIELDS),
        canonical_en=_first(node, _EN_FIELDS),
        aliases=_aliases(node),
        definition=str(node.get("definition") or ""),
    )


def _matches(term: GlossaryTerm, needle: str) -> bool:
    """True if the case-folded ``needle`` is a substring of any RU/EN/alias surface."""
    surfaces = (term.canonical_ru, term.canonical_en, *term.aliases)
    return any(needle in s.casefold() for s in surfaces if s)


def _resolve_labels(type_filter: str | None) -> list[str]:
    """Glossary labels to scan, narrowed by an optional ``type`` (§24.20 type filter)."""
    if type_filter is None:
        return list(GLOSSARY_LABELS)
    return [type_filter] if type_filter in GLOSSARY_LABELS else []


def build_glossary(
    store: KuzuGraphStore,
    *,
    q: str | None = None,
    type: str | None = None,
    limit: int = 100,
) -> list[GlossaryTerm]:
    """Build a domain glossary from the graph (§24.20 / §3.12).

    Gathers :Material / :Property / :Equipment / :Method nodes that carry a surface
    form, reads each one's canonical RU/EN names + aliases + definition, and returns
    up to ``limit`` :class:`GlossaryTerm` ordered by node id.

    Parameters:
    * ``q`` — case-insensitive substring filter over RU/EN canonical forms and aliases;
    * ``type`` — restrict to a single glossary label (outside the four -> empty list);
    * ``limit`` — max terms returned after filtering (``<= 0`` -> empty list).
    """
    labels = _resolve_labels(type)
    if not labels:
        return []
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels "
        "AND (n.name IS NOT NULL OR n.canonical_name IS NOT NULL "
        "OR n.aliases_text IS NOT NULL) RETURN n.id ORDER BY n.id",
        {"labels": labels},
    )
    needle = q.strip().casefold() if q and q.strip() else None
    terms: list[GlossaryTerm] = []
    for row in rows:
        if len(terms) >= limit:
            break
        node = store.get_node(row[0])
        if not node or "id" not in node:
            continue
        term = _term_from_node(node)
        if needle is not None and not _matches(term, needle):
            continue
        terms.append(term)
    _log.info("glossary.built", terms=len(terms), q=q, type=type)
    return terms
