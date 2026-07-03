"""Query expansion via synonyms / aliases (§12.13, pure python).

§12.13 asks that a user query be *broadened* (расширение запроса) before retrieval by
folding in the known surface forms of any entity it mentions. Given an ``alias_map``
(canonical -> list of aliases, RU|EN) built the same way as
:mod:`kg_retrievers.alias_index` — case-/punctuation-folded via
:func:`kg_common.canonical_key` — :func:`expand_query`:

* recognizes a mention (упоминание) whenever a canonical *or* one of its aliases appears
  as a contiguous phrase in the query (multi-word aliases included);
* for every recognized synonym group adds the *other* surface forms — so a canonical term
  pulls in its aliases and an alias pulls in the canonical (and its siblings);
* leaves unrecognized terms untouched, de-duplicates by folded key, and always keeps the
  original query terms first.

The result is a frozen :class:`ExpandedQuery` (``original`` / ``terms`` / ``added``) with an
``as_dict`` projection. This module is pure python: it reads the same folding *style* as
``alias_index`` but holds no store handles and does not import its private helpers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from kg_common import canonical_key


def _fold(surface: str) -> str:
    """Fold a surface form to its canonical comparison key (same style as alias_index)."""
    return canonical_key(surface)


def _tokens(text: str) -> list[str]:
    """Folded whitespace tokens of a surface/query, order-preserving (NOT de-duplicated).

    Unlike ``alias_index._tokens`` this keeps repeats: phrase matching needs positional
    tokens, and duplicate collapse happens later at the term level.
    """
    return _fold(text).split()


def _contains_phrase(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """True if ``needle`` tokens occur as a contiguous run inside ``haystack`` tokens."""
    n, m = len(haystack), len(needle)
    if m == 0 or m > n:
        return False
    first = needle[0]
    for i in range(n - m + 1):
        if haystack[i] == first and list(haystack[i : i + m]) == list(needle):
            return True
    return False


@dataclass(frozen=True)
class ExpandedQuery:
    """A query broadened with alias/synonym terms (§12.13).

    ``original`` is the raw query string; ``terms`` are the expanded search terms with the
    original query terms first (de-duplicated by folded key) followed by ``added`` — the
    alias/synonym surfaces pulled in for recognized mentions, in deterministic order.
    """

    original: str
    terms: tuple[str, ...]
    added: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "original": self.original,
            "terms": list(self.terms),
            "added": list(self.added),
        }


def expand_query(query: str, alias_map: Mapping[str, Sequence[str]]) -> ExpandedQuery:
    """Expand ``query`` with aliases/synonyms of any recognized entity mention (§12.13).

    ``alias_map`` maps a canonical surface to its aliases (canonical -> list[alias]). A
    synonym group ``[canonical, *aliases]`` is *recognized* when any of its surfaces appears
    as a contiguous phrase in the query; the group's remaining surfaces (those not already
    literally present) are then appended. Terms are de-duplicated by folded key with the
    original query terms kept first; an empty ``alias_map`` yields just the original terms.
    """
    q_tokens = _tokens(query)

    # Original query terms first, de-duplicated by folded key (original casing kept).
    seen: set[str] = set()
    terms: list[str] = []
    for raw in query.split():
        key = _fold(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        terms.append(raw)

    added: list[str] = []
    for canonical, aliases in alias_map.items():
        group = [canonical, *aliases]
        folded = [(surface, _tokens(surface)) for surface in group]
        recognized = any(toks and _contains_phrase(q_tokens, toks) for _, toks in folded)
        if not recognized:
            continue
        for surface, toks in folded:
            if not toks or _contains_phrase(q_tokens, toks):
                continue  # empty surface, or already literally in the query
            key = " ".join(toks)  # == _fold(surface)
            if key in seen:
                continue
            seen.add(key)
            added.append(surface)

    terms.extend(added)
    return ExpandedQuery(original=query, terms=tuple(terms), added=tuple(added))
