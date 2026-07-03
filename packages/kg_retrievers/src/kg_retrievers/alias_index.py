"""In-memory alias / fulltext entity index (§3.12 aliases_text, §8.4 entity_name_index).

§3.12 packs every entity's surface forms (name + canonical_name + pipe-separated
``aliases_text``, RU|EN) onto the node; §8.4 asks for an ``entity_name_index`` — a
fast, in-process lookup from a mention (упоминание) to a canonical entity id. This
module builds that index straight from a
:class:`~kg_retrievers.graph_store.KuzuGraphStore`:

* a **token -> {entity_ids}** inverted index (обратный индекс) powering token-overlap
  ranking in :meth:`AliasIndex.search`;
* an **exact alias -> id** map, folded to be case- and (lightly) declension-tolerant —
  RU/EN case-folding + whitespace/punctuation collapse — for O(1)
  :meth:`AliasIndex.lookup_exact`;
* a fuzzy fallback in :meth:`AliasIndex.resolve` (rapidfuzz ``token_set_ratio`` over the
  folded candidate alias strings) so near-misses / склонения still ground onto the
  right entity when the exact map misses.

The whole structure is rebuilt from the store on demand (``build_from_store``); it holds
no Kuzu handles, so it is cheap to snapshot and thread-safe to read.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from kg_common import canonical_key, get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

_log = get_logger("alias_index")

# rapidfuzz token_set_ratio (0..100) below which a fuzzy resolve is treated as "no
# match" — declension/typo near-misses score ~80+, unrelated strings well under this.
RESOLVE_MIN_SCORE: float = 60.0

# Surface fields folded into the index. ``aliases_text`` is pipe-separated (§3.12).
_NAME_FIELDS = ("name", "canonical_name")
_ALIAS_SEP = "|"


def _fold(surface: str) -> str:
    """Fold a surface form to its case-/punctuation-normalized key (§3.12).

    Reuses :func:`kg_common.canonical_key` (NFKC + lower + collapse) so RU/EN case and
    separators are neutralized. True declension tolerance comes from the fuzzy fallback
    in :meth:`AliasIndex.resolve`; here we only lowercase-fold.
    """
    return canonical_key(surface)


def _tokens(text: str) -> list[str]:
    """Distinct, order-preserving tokens (токены) of a folded surface/query."""
    return list(dict.fromkeys(_fold(text).split()))


def _surfaces(node: dict[str, object]) -> list[str]:
    """All surface strings for a node: name, canonical_name, each alias (§3.12)."""
    out: list[str] = []
    for key in _NAME_FIELDS:
        val = node.get(key)
        if val:
            out.append(str(val))
    aliases = node.get("aliases_text")
    if aliases:
        out.extend(part for part in str(aliases).split(_ALIAS_SEP) if part.strip())
    return out


@dataclass(frozen=True)
class AliasEntry:
    """One indexed entity's folded surface forms (§3.12 / §8.4)."""

    entity_id: str
    label: str
    name: str
    tokens: frozenset[str]
    aliases: tuple[str, ...]  # folded exact-match keys, de-duplicated

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "label": self.label,
            "name": self.name,
            "tokens": sorted(self.tokens),
            "aliases": list(self.aliases),
        }


class AliasIndex:
    """In-memory mention -> entity-id resolver over folded aliases (§3.12 / §8.4)."""

    def __init__(
        self,
        entries: dict[str, AliasEntry],
        inverted: dict[str, set[str]],
        exact: dict[str, str],
    ) -> None:
        self._entries = entries
        self._inverted = inverted
        self._exact = exact
        # Frozen candidate list for the fuzzy fallback (folded alias strings).
        self._alias_keys: tuple[str, ...] = tuple(exact.keys())

    # -- build -----------------------------------------------------------
    @classmethod
    def build_from_store(
        cls,
        store: KuzuGraphStore,
        *,
        labels: Iterable[str] = ENTITY_LABELS,
    ) -> AliasIndex:
        """Build the index from every resolvable :Entity node in the store (§8.4).

        Indexes each entity's name + canonical_name + ``aliases_text`` (split on ``|``).
        Idempotent w.r.t. the graph: two entities sharing a folded alias keep the first
        seen in the exact map (deterministic) while both appear in the inverted index.
        """
        label_list = list(labels)
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label IN $labels "
            "AND (n.name IS NOT NULL OR n.canonical_name IS NOT NULL "
            "OR n.aliases_text IS NOT NULL) RETURN n",
            {"labels": label_list},
        )
        entries: dict[str, AliasEntry] = {}
        inverted: dict[str, set[str]] = {}
        exact: dict[str, str] = {}
        for row in rows:
            node = store._node_dict(row[0])
            eid = node.get("id")
            if not eid:
                continue
            eid = str(eid)
            tokens: set[str] = set()
            folded_aliases: list[str] = []
            for surface in _surfaces(node):
                folded = _fold(surface)
                if not folded:
                    continue
                folded_aliases.append(folded)
                exact.setdefault(folded, eid)
                for tok in folded.split():
                    tokens.add(tok)
                    inverted.setdefault(tok, set()).add(eid)
            if not tokens:
                continue
            entries[eid] = AliasEntry(
                entity_id=eid,
                label=str(node.get("label", "Entity")),
                name=str(node.get("name") or node.get("canonical_name") or eid),
                tokens=frozenset(tokens),
                aliases=tuple(dict.fromkeys(folded_aliases)),
            )
        _log.info("alias_index.built", entities=len(entries), aliases=len(exact))
        return cls(entries, inverted, exact)

    # -- introspection ---------------------------------------------------
    def __len__(self) -> int:
        return len(self._entries)

    @property
    def n_aliases(self) -> int:
        """Number of distinct folded alias keys in the exact map."""
        return len(self._exact)

    def entry(self, entity_id: str) -> AliasEntry | None:
        return self._entries.get(entity_id)

    # -- lookup ----------------------------------------------------------
    def lookup_exact(self, surface: str) -> str | None:
        """Exact (case-folded) alias match -> entity id, else ``None`` (§8.4)."""
        if not surface or not surface.strip():
            return None
        return self._exact.get(_fold(surface))

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """Rank entities by token-overlap with ``query`` (§3.12 fulltext).

        Score = (distinct query tokens present in the entity) / (distinct query tokens),
        so a full surface match scores ``1.0``. Ties break by entity id for stability.
        """
        tokens = _tokens(query)
        if not tokens:
            return []
        counts: dict[str, int] = {}
        for tok in tokens:
            for eid in self._inverted.get(tok, ()):
                counts[eid] = counts.get(eid, 0) + 1
        n = float(len(tokens))
        scored = [(eid, hits / n) for eid, hits in counts.items()]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

    def resolve(
        self,
        mention: str,
        *,
        min_score: float = RESOLVE_MIN_SCORE,
    ) -> str | None:
        """Resolve a mention to one entity id: exact first, then fuzzy (§8.4).

        Falls back to rapidfuzz ``token_set_ratio`` over the folded alias candidates so a
        near-miss (typo / Russian склонение) still resolves; returns ``None`` when even the
        best fuzzy candidate scores below ``min_score``.
        """
        if not mention or not mention.strip():
            return None
        exact = self.lookup_exact(mention)
        if exact is not None:
            return exact
        if not self._alias_keys:
            return None
        folded = _fold(mention)
        if not folded:
            return None
        from rapidfuzz import fuzz, process

        best = process.extractOne(folded, self._alias_keys, scorer=fuzz.token_set_ratio)
        if best is None:
            return None
        alias, score, _ = best
        if score < min_score:
            return None
        return self._exact[alias]
