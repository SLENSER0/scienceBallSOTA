"""In-memory inverted index over community summaries for global search (§11.5).

GraphRAG's global-search step needs to find the community *summaries* most
relevant to a thematic query. In the server profile those summaries live in
Qdrant as embedded vectors; the embedded/offline profile keeps a deterministic
term-overlap index instead (ADR-0005, no external service).

``CommunityIndex`` reads the community-summary Finding nodes written by
:func:`kg_retrievers.community.detect_communities` (``label='Finding'`` with a
``community_id``) plus every community's member names/aliases/domain, then
indexes tokens → the set of communities that contain them. A query is scored by
the fraction of its tokens that hit each community (term overlap / перекрытие
терминов) — the same deterministic signal used by
:func:`kg_retrievers.community_search.global_search`, but precomputed once.

RU/EN terms (осмос / osmosis, вода / water …) tokenize uniformly so a Russian
query matches an English alias and vice-versa.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("community_index")

# Same tokenizer contract as community_search: RU+EN word chars, min length 3.
_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    """Lowercased word tokens of length ≥ 3 (RU/EN), matching community_search."""
    return {t.lower() for t in _TOKEN.findall(text or "") if len(t) >= 3}


@dataclass(frozen=True)
class CommunityIndex:
    """Searchable inverted index over community summaries (§11.5).

    - ``postings``: token → the set of ``community_id`` values that contain it
      (the inverted index / инвертированный индекс);
    - ``summaries``: ``community_id`` → summary text.
    """

    postings: dict[str, frozenset[int]] = field(default_factory=dict)
    summaries: dict[int, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"communities": len(self.summaries), "tokens": len(self.postings)}

    # -- build -----------------------------------------------------------
    @classmethod
    def build_from_store(cls, store: KuzuGraphStore) -> CommunityIndex:
        """Index the community-summary Finding nodes already present in *store*.

        Reads each ``label='Finding'`` summary node (with ``community_id``) and
        the searchable text of its members (name + aliases + domain), then maps
        every token to the communities that contain it. Call
        :func:`kg_retrievers.community.detect_communities` first to produce the
        summaries; on a store without any, the index is empty (not an error).
        """
        summaries: dict[int, str] = {}
        tokens_by_comm: dict[int, set[str]] = defaultdict(set)
        rows = store.rows(
            "MATCH (f:Node) WHERE f.label='Finding' AND f.community_id IS NOT NULL "
            "RETURN f.community_id, coalesce(f.text,'')",
            {},
        )
        for cid_raw, text in rows:
            cid = int(cid_raw)
            summaries[cid] = text
            tokens_by_comm[cid] |= _tokens(text)
            tokens_by_comm[cid] |= cls._member_tokens(store, cid)

        postings: dict[str, set[int]] = defaultdict(set)
        for cid, toks in tokens_by_comm.items():
            for tok in toks:
                postings[tok].add(cid)

        idx = cls(
            postings={tok: frozenset(cids) for tok, cids in postings.items()},
            summaries=summaries,
        )
        _log.info("community_index.build", **idx.as_dict())
        return idx

    @staticmethod
    def _member_tokens(store: KuzuGraphStore, cid: int) -> set[str]:
        """Tokens from a community's member names/aliases/domain (не Finding)."""
        rows = store.rows(
            "MATCH (n:Node) WHERE n.community_id=$c AND n.label<>'Finding' "
            "RETURN coalesce(n.name,''), coalesce(n.aliases_text,''), coalesce(n.domain,'')",
            {"c": cid},
        )
        out: set[str] = set()
        for name, aliases, domain in rows:
            out |= _tokens(f"{name} {aliases} {domain}")
        return out

    # -- query -----------------------------------------------------------
    def search(self, query: str, *, limit: int = 5) -> list[tuple[int, float]]:
        """Rank communities by query-token overlap; top *limit* first.

        Score = matched query tokens / total query tokens, so a community that
        covers more of the query outranks a partial match. Ties break by
        ascending ``community_id`` for determinism. Unknown/empty queries → [].
        """
        q = _tokens(query)
        if not q:
            return []
        matched: dict[int, int] = defaultdict(int)
        for tok in q:
            for cid in self.postings.get(tok, frozenset()):
                matched[cid] += 1
        scored = [(cid, hits / len(q)) for cid, hits in matched.items()]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:limit]

    def summary_for(self, community_id: int) -> str:
        """Return the summary text for *community_id* ('' if not indexed)."""
        return self.summaries.get(community_id, "")
