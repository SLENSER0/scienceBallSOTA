"""Entity-resolution candidate generation + DTO (§8.8).

Кандидаты на слияние / merge candidates. This module is pure Python (no Splink,
no store): it turns records into *blocked* pairs, bands a match score into a
decision, and packages the result as a frozen :class:`Candidate` DTO the
decision engine (§8.7) and review UI consume.

Pipeline shape::

    records --generate_pairs--> id-pairs --(scorer)--> scored_pairs
                                                            |
                                        build_candidates <--+
                                                            |
                                                            v
                                                    list[Candidate]

Blocking keeps ER tractable: instead of the full O(n^2) cartesian product we
only compare records that share a *block key*, so near-linear input growth does
not explode the pair count.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Decision bands / полосы решения (§8.7 domain of values).
AUTO_MERGE = "auto_merge"
REVIEW = "review"
REJECT = "reject"
_DECISIONS = frozenset({AUTO_MERGE, REVIEW, REJECT})


@dataclass(frozen=True)
class Candidate:
    """One merge candidate: a scored, banded record pair (§8.8).

    ``features`` carries the per-pair signals the scorer produced (name
    similarity, formula match, …) so a reviewer sees *why* the band was chosen.
    Frozen for safe reuse; ``as_dict`` yields a JSON-friendly copy.
    """

    left_id: str
    right_id: str
    score: float
    features: Mapping[str, Any] = field(default_factory=dict)
    decision: str = REJECT

    def __post_init__(self) -> None:
        if self.decision not in _DECISIONS:
            allowed = ", ".join(sorted(_DECISIONS))
            raise ValueError(f"decision must be one of {{{allowed}}}, got {self.decision!r}")

    def as_dict(self) -> dict[str, Any]:  # §8.8 serialization shape
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "score": round(float(self.score), 4),
            "features": dict(self.features),
            "decision": self.decision,
        }


def decide(score: float, *, auto: float = 0.9, review: float = 0.6) -> str:
    """Band a match *score* into ``auto_merge`` / ``review`` / ``reject``.

    Inclusive thresholds: ``score >= auto`` auto-merges, ``score >= review``
    goes to human review, everything below is rejected.
    """
    if score >= auto:
        return AUTO_MERGE
    if score >= review:
        return REVIEW
    return REJECT


def _block_of(record: Any, block_key: str | Callable[[Any], Any]) -> Any:
    """Extract the block value from *record* (callable or Mapping/attr key)."""
    if callable(block_key):
        return block_key(record)
    if isinstance(record, Mapping):
        return record.get(block_key)
    return getattr(record, block_key)


def _identity(record: Any) -> Any:
    """Stable id for *record*: ``id``/``unique_id`` field, else the value itself."""
    if isinstance(record, Mapping):
        for key in ("id", "unique_id"):
            if key in record:
                return record[key]
        raise KeyError("record mapping needs an 'id' or 'unique_id' field")
    return record


def _canon(a: Any, b: Any) -> tuple[Any, Any]:
    """Order a pair deterministically so (a, b) and (b, a) collapse to one key."""
    return (a, b) if str(a) <= str(b) else (b, a)


def generate_pairs(records: Iterable[Any], *, block_key: str | Callable[[Any], Any]) -> list[tuple]:
    """Blocked, symmetric, de-duplicated id pairs for *records* (§8.8).

    Only records that share the same non-``None`` block key are paired, which
    avoids the full cartesian product. Pairs are canonically ordered and each
    unordered pair appears at most once; self-pairs are dropped.
    """
    buckets: dict[Any, list[Any]] = {}
    for rec in records:
        block = _block_of(rec, block_key)
        if block is None:
            continue  # запись без блока не сравнивается / unblockable record — never paired
        buckets.setdefault(block, []).append(_identity(rec))

    pairs: list[tuple] = []
    seen: set[tuple] = set()
    for members in buckets.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                key = _canon(members[i], members[j])
                if key[0] == key[1] or key in seen:
                    continue  # self-pair or duplicate unordered pair
                seen.add(key)
                pairs.append(key)
    return pairs


def _unpack(item: Any) -> tuple[Any, Any, Any, Mapping[str, Any]]:
    """Normalize a scored pair to ``(left_id, right_id, score, features)``."""
    if isinstance(item, Mapping):
        return item["left_id"], item["right_id"], item["score"], item.get("features") or {}
    seq = tuple(item)
    if len(seq) == 3:
        left_id, right_id, score = seq
        return left_id, right_id, score, {}
    if len(seq) == 4:
        return seq[0], seq[1], seq[2], seq[3] or {}
    raise ValueError(f"scored pair must have 3 or 4 fields, got {len(seq)}")


def build_candidates(
    scored_pairs: Iterable[Any], *, auto: float = 0.9, review: float = 0.6
) -> list[Candidate]:
    """Band each scored pair into a :class:`Candidate`, preserving its features.

    Accepts ``(left_id, right_id, score)``, ``(left_id, right_id, score,
    features)`` tuples, or mappings with those keys. Empty input -> ``[]``.
    """
    candidates: list[Candidate] = []
    for item in scored_pairs:
        left_id, right_id, score, features = _unpack(item)
        candidates.append(
            Candidate(
                left_id=str(left_id),
                right_id=str(right_id),
                score=float(score),
                features=dict(features),
                decision=decide(float(score), auto=auto, review=review),
            )
        )
    return candidates
