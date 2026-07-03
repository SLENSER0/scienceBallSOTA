"""In-memory fulltext entity search (§8.4 embedded ``entity_name_index``).

The Neo4j deployment (§8.4) exposes an ``entity_name_index`` fulltext index so an
operator can type a partial / declined (склонённое) entity name and jump to the
canonical node. The embedded stack (Kuzu + local stores, §2) has no server-side
fulltext engine, so this module provides the **pure-python equivalent**: a small
in-process index over every entity's canonical name + aliases (RU/EN) that ranks
candidates by match quality.

Matching is case- and declension-tolerant without any external dependency:

* surfaces are *folded* with :func:`kg_common.canonical_key` (NFKC + lower +
  punctuation/whitespace collapse) — the same folding as
  :mod:`kg_retrievers.alias_index`;
* a **light Russian stemmer** (:func:`_stem`) strips common case/number endings
  (окончания) so ``осмоса`` and ``осмос`` collapse to one stem — this is what makes
  a declined query find the nominative name;
* ranking is tiered **exact > prefix > token > fuzzy** (:func:`SequenceMatcher`
  for the fuzzy fallback), so a typeahead prefix always outranks a mere near-miss.

Everything is plain python built from node dicts via
:meth:`EntityFulltext.build_from_nodes`; the index holds no store handles.

Kuzu note (§3): custom node properties are not queryable columns — callers that
build node dicts from a :class:`~kg_retrievers.graph_store.KuzuGraphStore` must
``RETURN`` the base node and read ``name`` / ``aliases_text`` via ``get_node`` /
``_node_dict`` before handing the dicts here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher

from kg_common import canonical_key

# -- ranking bands (base + span) --------------------------------------------
# Tiers never overlap: fuzzy(<=0.40) < token(<=0.70) < prefix(<=0.95) < exact(1.0).
EXACT_SCORE: float = 1.0
PREFIX_BASE: float = 0.80
PREFIX_SPAN: float = 0.15  # scaled by len(query)/len(alias) -> (0.80, 0.95]
TOKEN_BASE: float = 0.45
TOKEN_SPAN: float = 0.25  # scaled by token overlap fraction -> (0.45, 0.70]
FUZZY_BASE: float = 0.20
FUZZY_SPAN: float = 0.20  # scaled by SequenceMatcher ratio -> [~0.32, 0.40)
FUZZY_MIN: float = 0.60  # below this ratio a fuzzy candidate is dropped

# Surface fields folded into the index (§3.12). ``aliases_text`` is pipe-separated.
_NAME_FIELDS = ("name", "canonical_name")
_ALIAS_SEP = "|"

# Light Russian case/number endings (окончания), longest first so we strip greedily.
# Guarded by ``_MIN_STEM`` so short roots (e.g. "осмос") are never over-stripped.
_RU_ENDINGS: tuple[str, ...] = tuple(
    sorted(
        (
            "ого",
            "его",
            "ому",
            "ему",
            "ыми",
            "ими",
            "ами",
            "ями",
            "иях",
            "иям",
            "ой",
            "ей",
            "ом",
            "ем",
            "ах",
            "ях",
            "ов",
            "ев",
            "ий",
            "ый",
            "ая",
            "яя",
            "ое",
            "ее",
            "ые",
            "ие",
            "ью",
            "ия",
            "ии",
            "ию",
            "ям",
            "ах",
            "а",
            "я",
            "о",
            "е",
            "ы",
            "и",
            "у",
            "ю",
            "ь",
            "й",
        ),
        key=len,
        reverse=True,
    )
)
_MIN_STEM: int = 3


def _fold(surface: str) -> str:
    """Fold a surface/query to its case-/punctuation-normalized key (§3.12)."""
    return canonical_key(surface)


def _stem(token: str) -> str:
    """Strip one common Russian ending from a folded token (лёгкий стеммер).

    Only the longest ending that leaves a stem of at least :data:`_MIN_STEM`
    characters is removed, so ``осмоса`` -> ``осмос`` while ``осмос`` (and every
    Latin token) is returned unchanged.
    """
    for end in _RU_ENDINGS:
        if token.endswith(end) and len(token) - len(end) >= _MIN_STEM:
            return token[: -len(end)]
    return token


def _stem_tokens(folded: str) -> frozenset[str]:
    """Distinct stemmed tokens of a folded string."""
    return frozenset(_stem(tok) for tok in folded.split() if tok)


def _surfaces(node: Mapping[str, object]) -> list[str]:
    """All surface strings for a node: name, canonical_name, each alias (§3.12).

    Accepts either a pipe-separated ``aliases_text`` (§3.12 on-node form) or an
    ``aliases`` list; blanks and duplicates are dropped while preserving order.
    """
    out: list[str] = []
    for key in _NAME_FIELDS:
        val = node.get(key)
        if val:
            out.append(str(val))
    aliases = node.get("aliases_text")
    if aliases:
        out.extend(part for part in str(aliases).split(_ALIAS_SEP) if part.strip())
    listed = node.get("aliases")
    if isinstance(listed, (list, tuple)):
        out.extend(str(part) for part in listed if str(part).strip())
    # De-dup while preserving first-seen order.
    return list(dict.fromkeys(s for s in out if s.strip()))


@dataclass(frozen=True)
class EntityHit:
    """One ranked fulltext match (§8.4)."""

    id: str
    label: str  # display / canonical name shown to the operator
    type: str  # entity type / node category (e.g. "TechnologySolution")
    score: float  # tiered match score in (0, 1]
    matched_alias: str  # the original surface form that produced the match

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "score": self.score,
            "matched_alias": self.matched_alias,
        }


@dataclass(frozen=True)
class _Surface:
    """One folded surface form of an entity (name / canonical_name / alias)."""

    original: str
    folded: str
    stem_tokens: frozenset[str]


@dataclass(frozen=True)
class _Entry:
    """One indexed entity and every folded surface it can be matched on (§8.4)."""

    id: str
    label: str
    type: str
    surfaces: tuple[_Surface, ...]


class EntityFulltext:
    """In-memory, declension-tolerant fulltext search over entity names (§8.4)."""

    def __init__(self, entries: Iterable[_Entry]) -> None:
        self._entries: tuple[_Entry, ...] = tuple(entries)

    # -- build -----------------------------------------------------------
    @classmethod
    def build_from_nodes(cls, nodes: Iterable[Mapping[str, object]]) -> EntityFulltext:
        """Build the index from entity node dicts (§8.4).

        Each node needs an ``id``; its display ``label`` is taken from ``name`` /
        ``canonical_name`` (falling back to the id) and its ``type`` from the
        node's ``type`` or (raw-Kuzu convention) ``label`` field. Surfaces come
        from name + canonical_name + ``aliases_text`` / ``aliases`` (§3.12). Nodes
        without an id or any usable surface are skipped.
        """
        entries: list[_Entry] = []
        for node in nodes:
            raw_id = node.get("id")
            if not raw_id:
                continue
            eid = str(raw_id)
            surfaces: list[_Surface] = []
            for surface in _surfaces(node):
                folded = _fold(surface)
                if not folded:
                    continue
                surfaces.append(
                    _Surface(
                        original=surface,
                        folded=folded,
                        stem_tokens=_stem_tokens(folded),
                    )
                )
            if not surfaces:
                continue
            display = node.get("name") or node.get("canonical_name") or eid
            etype = node.get("type") or node.get("label") or "Entity"
            entries.append(
                _Entry(
                    id=eid,
                    label=str(display),
                    type=str(etype),
                    surfaces=tuple(surfaces),
                )
            )
        return cls(entries)

    # -- introspection ---------------------------------------------------
    def __len__(self) -> int:
        return len(self._entries)

    # -- scoring ---------------------------------------------------------
    @staticmethod
    def _score_surface(qf: str, q_stems: frozenset[str], surf: _Surface) -> float:
        """Best tiered score of query ``qf`` against one surface, ``0.0`` if none."""
        af = surf.folded
        if qf == af:
            return EXACT_SCORE
        if af.startswith(qf):  # typeahead prefix; qf strictly shorter than af here
            return round(PREFIX_BASE + PREFIX_SPAN * (len(qf) / len(af)), 4)
        if q_stems:
            inter = q_stems & surf.stem_tokens
            if inter:
                overlap = len(inter) / len(q_stems)
                return round(TOKEN_BASE + TOKEN_SPAN * overlap, 4)
        ratio = SequenceMatcher(None, qf, af).ratio()
        if ratio >= FUZZY_MIN:
            return round(FUZZY_BASE + FUZZY_SPAN * ratio, 4)
        return 0.0

    def _best(self, qf: str, q_stems: frozenset[str], entry: _Entry) -> tuple[float, str]:
        """Highest-scoring surface of ``entry`` -> ``(score, original_surface)``."""
        best_score = 0.0
        best_alias = ""
        for surf in entry.surfaces:
            score = self._score_surface(qf, q_stems, surf)
            if score > best_score:
                best_score = score
                best_alias = surf.original
        return best_score, best_alias

    # -- search ----------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        type: str | None = None,
        limit: int = 10,
    ) -> list[EntityHit]:
        """Rank entities matching ``query`` (§8.4).

        ``type`` restricts the result to one entity type/category; ``limit`` caps
        the number of hits. Ordering is by descending score then id (stable). An
        empty/blank query, or one with no candidate above the fuzzy floor, yields
        an empty list.
        """
        if not query or not query.strip():
            return []
        qf = _fold(query)
        if not qf:
            return []
        q_stems = _stem_tokens(qf)
        hits: list[EntityHit] = []
        for entry in self._entries:
            if type is not None and entry.type != type:
                continue
            score, alias = self._best(qf, q_stems, entry)
            if score <= 0.0:
                continue
            hits.append(
                EntityHit(
                    id=entry.id,
                    label=entry.label,
                    type=entry.type,
                    score=score,
                    matched_alias=alias,
                )
            )
        hits.sort(key=lambda h: (-h.score, h.id))
        return hits[:limit]


def build_from_nodes(nodes: Iterable[Mapping[str, object]]) -> EntityFulltext:
    """Module-level convenience factory mirroring :meth:`EntityFulltext.build_from_nodes`."""
    return EntityFulltext.build_from_nodes(nodes)
