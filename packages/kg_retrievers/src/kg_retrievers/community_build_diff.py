"""Diff of community structure across two build runs (§11.17).

Pure-python comparison of two *community builds* — mappings of a community id to
its set of member ids — with no dependency on the graph store. Communities are
matched across builds by the Jaccard overlap of their member sets:

- a pair of ``(old, new)`` communities whose Jaccard ``>= match_threshold`` is
  reported as **stable**;
- an old community that is the best match of **2+** new communities has been
  **split** into those new communities;
- **2+** old communities that best match a single new community have been
  **merged** into it;
- a new community matched by nothing is **appeared**; an old community matched
  by nothing has **disappeared**.

Дифф сообществ между двумя сборками: сопоставление по Жаккару множеств
участников (стабильные / появившиеся / исчезнувшие / слитые / разделённые).

The result is a frozen dataclass exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass

# A build maps a community id to the set of its member ids (участники).
Build = dict[int, set[str]]


def jaccard(a: set, b: set) -> float:
    """Jaccard overlap ``|a ∩ b| / |a ∪ b|`` of two sets (§11.17).

    Возвращает 0.0 для двух пустых множеств (пустое объединение).
    """
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _best_match(target: set, candidates: Build) -> int | None:
    """Candidate id with the highest positive Jaccard to ``target`` (§11.17).

    Ties are broken by the smaller id for deterministic output; ``None`` when no
    candidate shares any member (все пересечения пусты).
    """
    best_id: int | None = None
    best_score = 0.0
    for cid in sorted(candidates):
        score = jaccard(target, candidates[cid])
        if score > best_score:
            best_score = score
            best_id = cid
    return best_id


@dataclass(frozen=True)
class CommunityDiff:
    """Structural diff of communities between two builds (§11.17).

    - ``stable`` — ``(old_id, new_id)`` pairs with Jaccard ``>= threshold``;
    - ``appeared`` — new community ids matched by nothing;
    - ``disappeared`` — old community ids matched by nothing;
    - ``merged`` — ``((old_id, ...), new_id)``: several old collapse into one new;
    - ``split`` — ``(old_id, (new_id, ...))``: one old fans out into several new.

    All tuples are sorted for deterministic output.
    """

    stable: tuple[tuple[int, int], ...]
    appeared: tuple[int, ...]
    disappeared: tuple[int, ...]
    merged: tuple[tuple[tuple[int, ...], int], ...]
    split: tuple[tuple[int, tuple[int, ...]], ...]

    def as_dict(self) -> dict:
        return {
            "stable": [list(pair) for pair in self.stable],
            "appeared": list(self.appeared),
            "disappeared": list(self.disappeared),
            "merged": [[list(olds), new_id] for olds, new_id in self.merged],
            "split": [[old_id, list(news)] for old_id, news in self.split],
        }


def diff_builds(
    old: Build,
    new: Build,
    *,
    match_threshold: float = 0.5,
) -> CommunityDiff:
    """Diff two community builds by Jaccard of their member sets (§11.17).

    ``match_threshold`` is the minimum Jaccard for a ``(old, new)`` pair to be
    reported as *stable*. Splits (one old → many new) and merges (many old → one
    new) are derived from best-match grouping and take precedence over stable
    pairs; anything left unmatched is *appeared* (new) or *disappeared* (old).
    """
    # Best partner in the *other* build for every community (positive overlap).
    best_old_of_new = {n: _best_match(new[n], old) for n in new}
    best_new_of_old = {o: _best_match(old[o], new) for o in old}

    # split: an old id that is the best match of 2+ new communities.
    news_by_old: dict[int, list[int]] = {}
    for n, o in best_old_of_new.items():
        if o is not None:
            news_by_old.setdefault(o, []).append(n)
    split_map = {o: tuple(sorted(ns)) for o, ns in news_by_old.items() if len(ns) >= 2}

    # merged: a new id that is the best match of 2+ old communities.
    olds_by_new: dict[int, list[int]] = {}
    for o, n in best_new_of_old.items():
        if n is not None:
            olds_by_new.setdefault(n, []).append(o)
    merged_map = {n: tuple(sorted(os)) for n, os in olds_by_new.items() if len(os) >= 2}

    split_olds = set(split_map)
    split_news = {n for ns in split_map.values() for n in ns}
    merged_news = set(merged_map)
    merged_olds = {o for os in merged_map.values() for o in os}

    consumed_olds = split_olds | merged_olds
    consumed_news = split_news | merged_news

    # stable: mutual best matches at/above threshold, not already split/merged.
    stable: list[tuple[int, int]] = []
    for o in sorted(old):
        if o in consumed_olds:
            continue
        n = best_new_of_old[o]
        if n is None or n in consumed_news:
            continue
        if best_old_of_new.get(n) == o and jaccard(old[o], new[n]) >= match_threshold:
            stable.append((o, n))

    matched_olds = consumed_olds | {o for o, _ in stable}
    matched_news = consumed_news | {n for _, n in stable}

    disappeared = tuple(sorted(o for o in old if o not in matched_olds))
    appeared = tuple(sorted(n for n in new if n not in matched_news))

    merged = tuple(sorted((olds, n) for n, olds in merged_map.items()))
    split = tuple(sorted((o, news) for o, news in split_map.items()))

    return CommunityDiff(
        stable=tuple(stable),
        appeared=appeared,
        disappeared=disappeared,
        merged=merged,
        split=split,
    )
