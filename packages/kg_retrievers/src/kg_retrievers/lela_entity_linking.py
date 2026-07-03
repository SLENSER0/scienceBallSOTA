"""LELA-style zero-shot entity-linking rerank pipeline (§8 ER — entity resolution).

Reference implementation of the **LELA** zero-shot entity linker
(*"LELA: Zero-shot Entity Linking by List-wise Abstention"*, arXiv:2601.05192).
The authors' code is **to-be-released**; this is an independent **reference
implementation** built from the paper's description, not a port of official code.

Pipeline (paper §3), adapted onto the embedded stack (§2, no server-side ranker):

1. **BM25-lite candidate score.** The mention is scored against every candidate's
   surfaces (canonical name + RU/EN aliases) by delegating to the codebase's
   in-process fulltext / BM25-lite index :class:`kg_retrievers.entity_fulltext.
   EntityFulltext` (READ / reused, never edited). This yields a base retrieval
   score ``base ∈ (0, 1]`` per candidate — the LELA *retriever* stage.

2. **Pointwise rerank.** A cheap, model-free reranker boosts high-precision
   evidence: an **exact** fold-match of the mention against a candidate's
   *canonical name* adds :data:`EXACT_NAME_BOOST`; an exact match against one of
   its *aliases* adds the smaller :data:`ALIAS_BOOST`. ``score = base + boost`` —
   so exact-name ≻ exact-alias ≻ fuzzy, the LELA *rerank* stage.

3. **Self-consistency / abstention (NIL).** LELA abstains when the top candidate
   is not decisively better than the runner-up. If ``best.score − second.score``
   is below ``margin`` (:data:`NIL_MARGIN`) — or no candidate matched at all —
   the linker predicts **NIL** (``is_nil=True``, ``best=None``) instead of a
   possibly-wrong link. Otherwise it commits to the top candidate.

Everything is pure python built from candidate node dicts; the linker holds no
store handles. Kuzu note (§3): custom node properties are **not** queryable
columns — a caller assembling candidates from a
:class:`~kg_retrievers.graph_store.KuzuGraphStore` must ``RETURN`` the base node
and read ``name`` / ``aliases_text`` via ``get_node`` before handing dicts here;
the tests build a plain in-memory list of dicts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from kg_common import canonical_key
from kg_retrievers.entity_fulltext import EntityFulltext

# -- rerank + abstention constants (§3 LELA) --------------------------------
# Boosts stack on the BM25-lite base ∈ (0, 1]; exact-name always outranks
# exact-alias, which always outranks any fuzzy/prefix/token base match.
EXACT_NAME_BOOST: float = 1.0
ALIAS_BOOST: float = 0.5
# Minimal lead the winner must have over the runner-up to commit (else NIL).
NIL_MARGIN: float = 0.15

# Candidate surface fields (§3.12). ``aliases_text`` is pipe-separated on-node.
_NAME_FIELDS = ("name", "canonical_name")
_ALIAS_SEP = "|"


def _fold(surface: str) -> str:
    """Fold a surface/mention to its canonical comparison key (§3.12).

    Same folding as :mod:`kg_retrievers.entity_fulltext` — NFKC + lower +
    punctuation/whitespace collapse (RU/EN), so declension-insensitive equality.
    """
    return canonical_key(surface)


def _alias_surfaces(cand: Mapping[str, object]) -> list[str]:
    """Every *alias* surface of a candidate (excludes the canonical name).

    Reads a pipe-separated ``aliases_text`` (§3.12 on-node form) and/or an
    ``aliases`` list; blanks and duplicates are dropped, first-seen order kept.
    """
    out: list[str] = []
    text = cand.get("aliases_text")
    if text:
        out.extend(part for part in str(text).split(_ALIAS_SEP) if part.strip())
    listed = cand.get("aliases")
    if isinstance(listed, (list, tuple)):
        out.extend(str(part) for part in listed if str(part).strip())
    return list(dict.fromkeys(s for s in out if s.strip()))


def _name_surfaces(cand: Mapping[str, object]) -> list[str]:
    """Canonical name surface(s) of a candidate (``name`` / ``canonical_name``)."""
    out: list[str] = []
    for key in _NAME_FIELDS:
        val = cand.get(key)
        if val:
            out.append(str(val))
    return list(dict.fromkeys(s for s in out if s.strip()))


@dataclass(frozen=True)
class ScoredCandidate:
    """One reranked candidate: KB ``id`` + final LELA ``score`` (§8 ER)."""

    id: str
    score: float

    def as_dict(self) -> dict[str, object]:
        """Plain ``{id, score}`` projection for JSON / UI / logs."""
        return {"id": self.id, "score": self.score}


@dataclass(frozen=True)
class LinkResult:
    """Outcome of linking one mention (§8 ER).

    Атрибуты:
        mention:  original surface form that was linked.
        ranked:   candidates by descending ``score`` (top-``k``), each ``{id, score}``.
        best:     committed KB ``id`` — ``None`` when the linker abstains (NIL).
        is_nil:   ``True`` when the linker abstains (no / ambiguous evidence).
    """

    mention: str
    ranked: tuple[ScoredCandidate, ...]
    best: str | None
    is_nil: bool

    def as_dict(self) -> dict[str, object]:
        """Round-trip all fields; ``ranked`` becomes a list of ``{id, score}``."""
        return {
            "mention": self.mention,
            "ranked": [cand.as_dict() for cand in self.ranked],
            "best": self.best,
            "is_nil": self.is_nil,
        }


def _bm25_lite_base(mention: str, candidates: list[Mapping[str, object]]) -> dict[str, float]:
    """BM25-lite retrieval score per candidate id via the fulltext index (§3 LELA).

    Delegates to :class:`kg_retrievers.entity_fulltext.EntityFulltext` — the
    codebase's in-process fulltext / BM25-lite scorer — and maps each hit id to
    its tiered match score ``∈ (0, 1]``. Candidates with no surface match are
    absent from the returned mapping (base ``0``). Duplicate ids keep the best.
    """
    index = EntityFulltext.build_from_nodes(candidates)
    base: dict[str, float] = {}
    for hit in index.search(mention, limit=len(candidates) or 1):
        if hit.score > base.get(hit.id, 0.0):
            base[hit.id] = hit.score
    return base


def _rerank_boost(mention_folded: str, cand: Mapping[str, object]) -> float:
    """Pointwise rerank boost for a candidate (§3 LELA rerank stage).

    Exact fold-match on the *canonical name* → :data:`EXACT_NAME_BOOST`; else an
    exact fold-match on any *alias* → :data:`ALIAS_BOOST`; else ``0.0``.
    """
    if any(mention_folded == _fold(name) for name in _name_surfaces(cand)):
        return EXACT_NAME_BOOST
    if any(mention_folded == _fold(alias) for alias in _alias_surfaces(cand)):
        return ALIAS_BOOST
    return 0.0


def link_entities(
    mention: str,
    candidates: Iterable[Mapping[str, object]],
    *,
    top_k: int = 5,
    margin: float = NIL_MARGIN,
) -> LinkResult:
    """Link ``mention`` to one of ``candidates`` (LELA zero-shot rerank, §8 ER).

    Каждый кандидат — dict с ``id`` и хотя бы одной поверхностью (``name`` /
    ``canonical_name`` / ``aliases`` / ``aliases_text``, §3.12). Пайплайн: (1)
    BM25-lite базовая оценка через :class:`~kg_retrievers.entity_fulltext.
    EntityFulltext`; (2) pointwise-rerank — буст за точное совпадение имени/алиаса;
    (3) self-consistency: если лидер не опережает второго на ``margin`` (или ни
    один кандидат не совпал) — воздержаться (``is_nil=True``, ``best=None``).

    ``top_k`` ограничивает длину ``ranked`` (маргин всё равно считается по полному
    ранжированию). Возвращает :class:`LinkResult`; порядок — по убыванию ``score``,
    ничьи — по возрастанию ``id``.
    """
    cand_list = [c for c in candidates if c.get("id")]
    mention_folded = _fold(mention)

    base = _bm25_lite_base(mention, cand_list) if cand_list and mention_folded else {}

    scored: list[ScoredCandidate] = []
    for cand in cand_list:
        cid = str(cand["id"])
        total = base.get(cid, 0.0) + _rerank_boost(mention_folded, cand)
        if total > 0.0:
            scored.append(ScoredCandidate(id=cid, score=round(total, 4)))

    scored.sort(key=lambda c: (-c.score, c.id))

    second = scored[1].score if len(scored) >= 2 else 0.0
    lead = scored[0].score - second if scored else 0.0
    is_nil = (not scored) or lead < margin

    ranked = tuple(scored[: max(top_k, 0)])
    best = None if is_nil else ranked[0].id
    return LinkResult(mention=mention, ranked=ranked, best=best, is_nil=is_nil)
