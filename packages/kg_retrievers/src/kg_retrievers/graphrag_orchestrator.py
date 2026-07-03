"""GraphRAG global-vs-local routing + merge (§11.8).

GraphRAG answers two shapes of question over the community graph (§11.7):

- **global search** — broad/thematic questions ("обзор основных технологий
  очистки воды", "main technology clusters") map-reduce community *summaries*
  (кластеры знаний) into one answer;
- **local search** — specific-entity questions ("reverse osmosis desalination")
  gather a seed entity's community + immediate neighbours.

This module adds the *router* that §11.8 calls for: :func:`graphrag_answer`
inspects the query with a deterministic heuristic (:func:`route_query`), dispatches
to the existing :func:`~kg_retrievers.community_search.global_search` /
:func:`~kg_retrievers.community_search.local_search`, and merges the cited source
documents (документы) and Evidence ids (эвиденс) via
:func:`~kg_retrievers.graphrag_citations.trace_answer_sources` so the answer stays
auditable (§11.11).

Offline-safe and deterministic (no LLM): the heuristic is a term-marker + entity
name-resolution rule, and all merged id lists are deduplicated and sorted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from kg_common import get_logger
from kg_retrievers.community_search import global_search, local_search
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.graphrag_citations import trace_answer_sources
from kg_schema.labels import ENTITY_LABELS

_log = get_logger("graphrag_orchestrator")

_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

# Thematic markers (RU/EN) that signal a broad/aggregate question -> global search.
# Matched against query *tokens* (not substrings) so "domain" never triggers "main".
_GLOBAL_WORDS: frozenset[str] = frozenset(
    {
        # -- EN --
        "overview",
        "landscape",
        "main",
        "theme",
        "themes",
        "trend",
        "trends",
        "cluster",
        "clusters",
        "category",
        "categories",
        "types",
        "kinds",
        "compare",
        "comparison",
        "summary",
        "summarize",
        "across",
        "overall",
        "general",
        # -- RU --
        "обзор",
        "основные",
        "какие",
        "тема",
        "темы",
        "тренд",
        "тренды",
        "кластер",
        "кластеры",
        "категории",
        "виды",
        "сравнить",
        "сравнение",
        "ландшафт",
        "направления",
        "обобщение",
    }
)
# Multi-word thematic markers, matched as substrings on the lowered query.
_GLOBAL_PHRASES: tuple[str, ...] = ("what are", "list of", "types of", "kinds of")

# A short query naming an entity is a local lookup; long descriptive ones lean global.
_LOCAL_MAX_TOKENS = 6
# Fraction of query tokens covered by a single entity's name to force a local route.
_LOCAL_COVERAGE = 0.5

_VALID_MODES = frozenset({"auto", "global", "local"})


def _tokens(text: str) -> set[str]:
    """Lowercased alnum tokens of length >= 3 (RU/EN)."""
    return {t.lower() for t in _TOKEN.findall(text or "") if len(t) >= 3}


@dataclass(frozen=True)
class GraphRagResult:
    """Routed GraphRAG answer with merged, auditable citations (§11.8 / §11.11).

    Attributes:
        query: the original user query.
        mode_used: ``"global"`` or ``"local"`` — the branch actually taken.
        communities: community ids (кластеры) that backed the answer, sorted.
        local_seeds: entity ids that anchored a local search (empty for global).
        doc_ids: deduplicated source-document ids (документы), sorted.
        evidence_ids: deduplicated Evidence node ids (эвиденс), sorted.
    """

    query: str
    mode_used: str
    communities: list[int] = field(default_factory=list)
    local_seeds: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (copies the lists)."""
        return {
            "mode_used": self.mode_used,
            "communities": list(self.communities),
            "local_seeds": list(self.local_seeds),
            "doc_ids": list(self.doc_ids),
            "evidence_ids": list(self.evidence_ids),
        }


def _looks_global(query: str, q_tokens: set[str]) -> bool:
    """True if the query carries a thematic/aggregate marker (RU/EN)."""
    if q_tokens & _GLOBAL_WORDS:
        return True
    low = (query or "").lower()
    return any(phrase in low for phrase in _GLOBAL_PHRASES)


def _resolve_seeds(store: KuzuGraphStore, q_tokens: set[str], *, limit: int) -> list[str]:
    """Rank entity nodes by name/alias token overlap with the query.

    Returns the ids of entities (:data:`ENTITY_LABELS`) that share >= 1 token with
    the query, best-first, deterministically tie-broken by id. Chunk/Finding/
    Evidence nodes are excluded — only resolvable entities can seed a local search.
    """
    if not q_tokens:
        return []
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $l "
        "RETURN n.id, coalesce(n.name,''), coalesce(n.aliases_text,'')",
        {"l": list(ENTITY_LABELS)},
    )
    scored: list[tuple[int, str]] = []
    for nid, name, aliases in rows:
        overlap = len(q_tokens & (_tokens(name) | _tokens(aliases)))
        if overlap:
            scored.append((overlap, nid))
    # higher overlap first; stable id order for ties -> deterministic output.
    scored.sort(key=lambda p: (-p[0], p[1]))
    return [nid for _, nid in scored[:limit]]


def route_query(store: KuzuGraphStore, query: str) -> str:
    """Heuristic router: pick ``"global"`` vs ``"local"`` for *query* (§11.8).

    Rule (deterministic, query-only):

    1. an explicit thematic marker ("обзор", "main", "clusters", ...) -> global;
    2. otherwise, if the query resolves to a specific entity — either it mostly
       *is* that entity's name (coverage >= :data:`_LOCAL_COVERAGE`) or it is a
       short focused query (<= :data:`_LOCAL_MAX_TOKENS` tokens) — -> local;
    3. everything else (long, unresolved, or empty) -> global.
    """
    q_tokens = _tokens(query)
    if not q_tokens:
        return "global"
    if _looks_global(query, q_tokens):
        return "global"
    seeds = _resolve_seeds(store, q_tokens, limit=1)
    if seeds:
        # best-seed coverage: how much of the query that top entity's name explains.
        node = store.get_node(seeds[0]) or {}
        name_tokens = _tokens(str(node.get("name", "")))
        name_tokens |= _tokens(str(node.get("aliases_text", "")))
        coverage = len(q_tokens & name_tokens) / len(q_tokens)
        if coverage >= _LOCAL_COVERAGE or len(q_tokens) <= _LOCAL_MAX_TOKENS:
            return "local"
    return "global"


def _merge_sources(store: KuzuGraphStore, member_ids: list[str]) -> tuple[list[str], list[str]]:
    """Trace SUPPORTED_BY provenance of *member_ids* -> ``(doc_ids, evidence_ids)``."""
    src = trace_answer_sources(store, member_ids)
    return src.doc_ids, src.evidence_ids


def _answer_global(store: KuzuGraphStore, query: str, *, limit: int) -> GraphRagResult:
    """Global branch: score community summaries, merge their citations (§11.7)."""
    ans = global_search(store, query, limit=limit)
    communities = sorted({int(c.community_id) for c in ans.communities})
    member_ids = [m for c in ans.communities for m in c.member_ids]
    doc_ids, evidence_ids = _merge_sources(store, member_ids)
    return GraphRagResult(
        query=query,
        mode_used="global",
        communities=communities,
        local_seeds=[],
        doc_ids=doc_ids,
        evidence_ids=evidence_ids,
    )


def _answer_local(store: KuzuGraphStore, query: str, *, limit: int) -> GraphRagResult:
    """Local branch: resolve seed entities, gather their context, merge citations."""
    seeds = _resolve_seeds(store, _tokens(query), limit=limit)
    used_seeds: list[str] = []
    comms: set[int] = set()
    members: set[str] = set()
    for seed in seeds:
        out = local_search(store, seed, limit=limit)
        if not out.get("found"):
            continue
        used_seeds.append(out["seed"])
        members.add(out["seed"])
        members.update(out.get("members", []))
        members.update(out.get("neighbors", []))
        cid = out.get("community_id")
        if cid is not None:
            comms.add(int(cid))
    doc_ids, evidence_ids = _merge_sources(store, sorted(members))
    return GraphRagResult(
        query=query,
        mode_used="local",
        communities=sorted(comms),
        local_seeds=used_seeds,
        doc_ids=doc_ids,
        evidence_ids=evidence_ids,
    )


def graphrag_answer(
    store: KuzuGraphStore,
    query: str,
    *,
    mode: str = "auto",
    limit: int = 5,
) -> GraphRagResult:
    """Route *query* to global or local GraphRAG and merge cited sources (§11.8).

    Args:
        store: the community-annotated graph store.
        query: user question (RU/EN).
        mode: ``"auto"`` (route via :func:`route_query`), or force ``"global"`` /
            ``"local"``.
        limit: fan-out cap for communities (global) or seeds/context (local).

    Returns:
        A :class:`GraphRagResult` whose ``doc_ids`` / ``evidence_ids`` are the
        deduplicated, sorted citations backing the chosen branch. Unknown queries,
        empty stores, and empty queries degrade gracefully to an empty result.

    Raises:
        ValueError: if *mode* is not one of ``auto`` / ``global`` / ``local``.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}")
    chosen = route_query(store, query) if mode == "auto" else mode
    if chosen == "local":
        result = _answer_local(store, query, limit=limit)
    else:
        result = _answer_global(store, query, limit=limit)
    _log.info(
        "graphrag.answer",
        mode=chosen,
        communities=len(result.communities),
        seeds=len(result.local_seeds),
        docs=len(result.doc_ids),
        evidence=len(result.evidence_ids),
    )
    return result
