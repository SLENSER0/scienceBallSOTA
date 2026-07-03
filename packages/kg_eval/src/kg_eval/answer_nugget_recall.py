"""Answer nugget recall — key-fact coverage of a free-text answer (§23.31).

LitQA2 / nugget-eval style scoring: a gold answer is a *set of required
nuggets* (key facts), and we ask how many of them a free-text answer covers.
This is distinct from:

* :mod:`kg_eval.claim_support` — citation + numeric support of claims, and
* :mod:`kg_eval.citation_check` — existence of cited evidence ids.

Here we care only about the *content* of the answer text — RU: покрытие
ключевых фактов свободного ответа.

Definitions — RU/EN:

* ``nugget`` — a Mapping ``{'id': str, 'aliases': list[str],
  'weight': float=1.0}``; a required key fact / обязательный факт.
* A nugget is *covered* iff any of its aliases (or, when ``aliases`` is empty,
  its ``id`` text) appears as a **normalized substring** of the answer /
  факт покрыт, если любой из его синонимов встречается в ответе.
* Normalization — ``casefold`` + collapse of runs of whitespace to a single
  space, applied to both the answer and each alias / нормализация обеих сторон.
* ``recall`` — ``n_covered / n`` (unweighted) / полнота без весов.
* ``weighted_recall`` — ``covered_weight / total_weight`` / взвешенная полнота.
* ``missing`` — sorted ids of nuggets that were not covered / пропущенные id.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Casefold and collapse whitespace runs (RU: нормализация текста)."""
    return _WS_RE.sub(" ", str(text)).strip().casefold()


@dataclass(frozen=True)
class NuggetHit:
    """Frozen per-nugget coverage record (§23.31)."""

    id: str
    covered: bool
    matched_alias: str | None

    def as_dict(self) -> dict[str, object]:
        """Return a plain-dict view (RU: как словарь)."""
        return {
            "id": self.id,
            "covered": bool(self.covered),
            "matched_alias": self.matched_alias,
        }


@dataclass(frozen=True)
class NuggetReport:
    """Frozen nugget-recall report over a single answer (§23.31)."""

    n: int
    n_covered: int
    recall: float
    weighted_recall: float
    missing: tuple[str, ...]
    hits: tuple[NuggetHit, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a plain-dict view with rounded rates (RU: как словарь)."""
        return {
            "n": int(self.n),
            "n_covered": int(self.n_covered),
            "recall": round(float(self.recall), 6),
            "weighted_recall": round(float(self.weighted_recall), 6),
            "missing": list(self.missing),
            "hits": [h.as_dict() for h in self.hits],
        }


def score_nuggets(
    answer: str,
    nuggets: Iterable[Mapping[str, object]],
) -> NuggetReport:
    """Score nugget coverage of ``answer`` (LitQA2 / nugget-eval style, §23.31).

    Each nugget is a Mapping ``{'id', 'aliases', 'weight'}``.  A nugget is
    covered iff any alias — or, when ``aliases`` is empty, its ``id`` text —
    appears as a normalized substring of the answer.  Both sides are normalized
    via ``casefold`` + whitespace collapse.

    ``recall`` is ``n_covered / n``; ``weighted_recall`` is covered weight over
    total weight; ``missing`` holds the sorted ids of uncovered nuggets.  An
    empty ``nuggets`` iterable raises :class:`ValueError`.
    """
    nugget_list = list(nuggets)
    if not nugget_list:
        raise ValueError("nuggets must be non-empty / список фактов пуст")

    norm_answer = _normalize(answer)

    hits: list[NuggetHit] = []
    covered_weight = 0.0
    total_weight = 0.0
    missing_ids: list[str] = []

    for nugget in nugget_list:
        nid = str(nugget["id"])
        weight = float(nugget.get("weight", 1.0))
        aliases = list(nugget.get("aliases") or [])
        candidates = aliases if aliases else [nid]

        total_weight += weight

        matched_alias: str | None = None
        for alias in candidates:
            if _normalize(alias) in norm_answer:
                matched_alias = str(alias)
                break

        covered = matched_alias is not None
        if covered:
            covered_weight += weight
        else:
            missing_ids.append(nid)

        hits.append(NuggetHit(id=nid, covered=covered, matched_alias=matched_alias))

    n = len(nugget_list)
    n_covered = sum(1 for h in hits if h.covered)
    recall = n_covered / n
    weighted_recall = covered_weight / total_weight if total_weight else 0.0

    return NuggetReport(
        n=n,
        n_covered=n_covered,
        recall=recall,
        weighted_recall=weighted_recall,
        missing=tuple(sorted(missing_ids)),
        hits=tuple(hits),
    )
