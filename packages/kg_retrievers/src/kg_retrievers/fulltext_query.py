"""Lucene query builder for the Neo4j fulltext index (§3.12 ``entity_name_index``).

:mod:`kg_retrievers.entity_fulltext` does the pure-python in-memory matching for the
embedded stack (§2). The **server** deployment (§8.4) instead calls
``db.index.fulltext.queryNodes('entity_name_index', <lucene>)`` — which needs a
*Lucene query string*, not a folded surface. Feeding a raw entity name straight in is
unsafe: names carry Lucene operator characters (``AA-2024``, ``Al-Cu (2024)``,
``ratio:1``) that would be parsed as syntax or throw a ``ParseException``.

This module builds that string safely:

* :func:`escape_lucene` backslash-escapes every Lucene special character so a surface
  is matched **literally** (буквально);
* :func:`build_entity_query` tokenises a free-text query on whitespace, escapes each
  token, and ``OR``-joins them (optionally appending ``~1`` for fuzzy / declined —
  склонённые — matches);
* :func:`build_alias_query` ``OR``-joins several already-known aliases into one query.

Each builder returns a frozen :class:`FulltextQuery` carrying the target ``index``, the
original ``raw`` text, and the assembled ``lucene`` string, with :meth:`~FulltextQuery.
as_dict` for JSON / logging.

Kuzu note (§3): custom node properties are not queryable columns — this module only
assembles the query string; callers ``RETURN`` base columns and read others via
``get_node`` before/after issuing the fulltext lookup.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Default fulltext index name (§8.4). Kept in one place so builders stay consistent.
DEFAULT_INDEX: str = "entity_name_index"

# Lucene special characters that must be backslash-escaped to match literally.
# Spec order (§3.12): + - && || ! ( ) { } [ ] ^ " ~ * ? : \ /
_LUCENE_SPECIALS: frozenset[str] = frozenset('+-!(){}[]^"~*?:\\/&|')

# Token joiner and the per-token fuzzy suffix (Lucene edit-distance 1).
_OR_JOIN: str = " OR "
_FUZZY_SUFFIX: str = "~1"


def escape_lucene(term: str) -> str:
    """Backslash-escape Lucene special characters so ``term`` matches literally.

    Экранирует спецсимволы Lucene, чтобы имя искалось буквально, а не как синтаксис.
    """
    out: list[str] = []
    for ch in term:
        if ch in _LUCENE_SPECIALS:
            out.append("\\")
        out.append(ch)
    return "".join(out)


@dataclass(frozen=True, slots=True)
class FulltextQuery:
    """A ready-to-run Lucene query for ``db.index.fulltext.queryNodes`` (§3.12).

    Готовый Lucene-запрос: ``index`` — имя индекса, ``raw`` — исходный текст,
    ``lucene`` — собранная строка запроса.
    """

    index: str
    raw: str
    lucene: str

    def as_dict(self) -> dict[str, str]:
        """Return a plain JSON-friendly dict for logging / API payloads."""
        return {"index": self.index, "raw": self.raw, "lucene": self.lucene}


def build_entity_query(
    text: str,
    *,
    fuzzy: bool = False,
    index: str = DEFAULT_INDEX,
) -> FulltextQuery:
    """Build an ``OR``-joined Lucene query from free-text ``text`` (§3.12).

    Tokenises on whitespace, escapes each token, and joins with ``' OR '``; when
    ``fuzzy`` each token gets a ``~1`` suffix (edit-distance 1) so declined /
    misspelled surfaces still match. Empty / whitespace-only ``text`` yields ``''``.

    Токенизирует по пробелам, экранирует и объединяет через ``OR`` (при ``fuzzy`` —
    с суффиксом ``~1``).
    """
    tokens = text.split()
    parts: list[str] = []
    for tok in tokens:
        escaped = escape_lucene(tok)
        parts.append(escaped + _FUZZY_SUFFIX if fuzzy else escaped)
    return FulltextQuery(index=index, raw=text, lucene=_OR_JOIN.join(parts))


def build_alias_query(
    aliases: Sequence[str],
    index: str = DEFAULT_INDEX,
) -> FulltextQuery:
    """Build an ``OR``-joined Lucene query from known ``aliases`` (§3.12).

    Each alias is escaped **whole** (whitespace preserved) and the escaped aliases are
    joined with ``' OR '``; the ``raw`` text mirrors that same join. Empty / blank
    aliases are skipped so no dangling ``OR`` is produced.

    Объединяет известные синонимы через ``OR``, экранируя каждый целиком.
    """
    kept = [a for a in aliases if a and a.strip()]
    escaped = [escape_lucene(a) for a in kept]
    return FulltextQuery(
        index=index,
        raw=_OR_JOIN.join(kept),
        lucene=_OR_JOIN.join(escaped),
    )
