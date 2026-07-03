"""§15.9/§23 gap-closure planning via greedy experiment set-cover (pure python, no store).

RU: Планирование закрытия пробелов (§15.9/§23). Жадный «set-cover»: даны открытые
пробелы ``gaps`` (id + опциональный вес) и набор кандидатов-экспериментов, каждый из
которых закрывает подмножество пробелов ``closes`` за стоимость ``cost``. Алгоритм
жадно выбирает эксперимент с максимальным отношением «вес вновь покрытых пробелов /
стоимость», разрывая ничьи меньшей стоимостью, затем ``experiment_id`` по алфавиту.
Возвращает неизменяемый план :class:`ClosurePlan`. Чистый python: граф/стор не трогает.
EN: Gap-closure planning (§15.9/§23). A greedy weighted set-cover: given open ``gaps``
(id + optional weight) and candidate experiments each closing a subset ``closes`` at a
``cost``, greedily pick the experiment maximizing newly-covered gap weight / cost, with
ties broken by lower cost then ``experiment_id``. Returns an immutable
:class:`ClosurePlan`. Pure python — it touches no graph/store.

Kuzu note: custom node props are not queryable columns — a caller assembling ``gaps``
or ``candidates`` from Kuzu must RETURN base columns and read the rest via
``get_node()`` before building the plain dicts this module consumes.
"""

from __future__ import annotations

from dataclasses import dataclass


def _gap_ids_and_weights(
    gaps: list, weights: dict[str, float] | None
) -> tuple[list[str], dict[str, float]]:
    """Normalise ``gaps`` into an ordered id list + per-id weight map (§15.9).

    Each gap is either a bare id (``str``) or a mapping with a ``gap_id`` key and an
    optional ``weight``. The explicit ``weights`` argument overrides any inline weight;
    a missing weight defaults to ``1.0``. Ids preserve first-seen order and dedupe.
    """
    weights = weights or {}
    ordered: list[str] = []
    weight_map: dict[str, float] = {}
    for gap in gaps:
        if isinstance(gap, str):
            gid, inline = gap, None
        elif isinstance(gap, dict):
            if "gap_id" not in gap:
                raise ValueError(f"gap dict must contain 'gap_id', got {gap!r}")
            gid = str(gap["gap_id"])
            inline = gap.get("weight")
        else:
            raise ValueError(f"gap must be str or dict, got {gap!r}")
        if gid in weight_map:
            continue  # dedupe: first occurrence wins
        if gid in weights:
            w = float(weights[gid])
        elif inline is not None:
            w = float(inline)
        else:
            w = 1.0
        if w < 0:
            raise ValueError(f"weight for gap {gid!r} must be >= 0, got {w!r}")
        ordered.append(gid)
        weight_map[gid] = w
    return ordered, weight_map


def _candidate_closes(candidate: dict, gap_id_set: set[str]) -> tuple[str, frozenset[str], float]:
    """Extract ``(experiment_id, closes∩open_gaps, cost)`` from one candidate (§15.9).

    ``closes`` is intersected with the open-gap id set so that experiments claiming
    already-unknown gaps do not inflate coverage. ``cost`` defaults to ``1.0`` and must
    be strictly positive (a zero-cost experiment would make the ratio ill-defined).
    """
    if "experiment_id" not in candidate:
        raise ValueError(f"candidate must contain 'experiment_id', got {candidate!r}")
    exp_id = str(candidate["experiment_id"])
    closes = frozenset(str(g) for g in candidate.get("closes", ())) & gap_id_set
    cost = float(candidate.get("cost", 1.0))
    if cost <= 0:
        raise ValueError(f"candidate {exp_id!r} cost must be > 0, got {cost!r}")
    return exp_id, closes, cost


@dataclass(frozen=True)
class ClosurePlan:
    """Immutable result of a greedy gap-closure plan (§15.9/§23).

    ``chosen`` are the picked ``experiment_id`` values in selection order; ``closed_gap_ids``
    the open gaps they cover (selection order, deduped); ``uncovered_gap_ids`` the open
    gaps left after the plan; ``total_cost`` the summed cost of ``chosen``; and
    ``coverage_ratio`` the fraction of open-gap *weight* covered, always in ``[0, 1]``.
    """

    chosen: list[str]
    closed_gap_ids: list[str]
    uncovered_gap_ids: list[str]
    total_cost: float
    coverage_ratio: float

    def as_dict(self) -> dict:
        """Plain-dict projection for JSON dump / round-trip (§15.9, house style)."""
        return {
            "chosen": list(self.chosen),
            "closed_gap_ids": list(self.closed_gap_ids),
            "uncovered_gap_ids": list(self.uncovered_gap_ids),
            "total_cost": self.total_cost,
            "coverage_ratio": self.coverage_ratio,
        }


def plan_closures(
    gaps: list,
    candidates: list,
    *,
    weights: dict[str, float] | None = None,
    max_experiments: int | None = None,
) -> ClosurePlan:
    """Greedy weighted set-cover over experiments closing open gaps (§15.9/§23).

    ``gaps`` are open-gap ids (bare ``str`` or ``{gap_id, weight?}`` dicts); ``candidates``
    are ``{experiment_id, closes: list[gap_id], cost: float=1.0}`` dicts. Each greedy step
    picks the candidate maximizing *newly-covered* gap weight / cost, breaking ties by lower
    cost then ``experiment_id``. Candidates covering no new gap are never picked. Stops when
    every open gap is covered, no candidate adds coverage, or ``max_experiments`` is reached.

    ``weights`` overrides inline gap weights (default ``1.0`` each). ``coverage_ratio`` is the
    covered fraction of total open-gap weight (``1.0`` when total weight is ``0``).
    """
    if max_experiments is not None and max_experiments < 0:
        raise ValueError(f"max_experiments must be >= 0, got {max_experiments!r}")

    gap_ids, weight_map = _gap_ids_and_weights(gaps, weights)
    gap_id_set = set(gap_ids)
    total_weight = sum(weight_map.values())

    parsed = [_candidate_closes(c, gap_id_set) for c in candidates]

    remaining = set(gap_ids)  # still-open gap ids
    chosen: list[str] = []
    closed_order: list[str] = []  # gaps in the order they get closed
    total_cost = 0.0
    used: set[str] = set()  # experiment_ids already picked

    while remaining:
        if max_experiments is not None and len(chosen) >= max_experiments:
            break
        best: tuple[str, frozenset[str], float] | None = None
        best_key: tuple[float, float, str] | None = None
        for exp_id, closes, cost in parsed:
            if exp_id in used:
                continue
            new_gaps = closes & remaining
            if not new_gaps:
                continue
            gained = sum(weight_map[g] for g in new_gaps)
            ratio = gained / cost
            # Maximise ratio; tie-break by lower cost, then lex/experiment_id.
            key = (-ratio, cost, exp_id)
            if best_key is None or key < best_key:
                best_key = key
                best = (exp_id, closes, cost)
        if best is None:
            break  # no remaining candidate covers a new gap
        exp_id, closes, cost = best
        used.add(exp_id)
        chosen.append(exp_id)
        total_cost += cost
        for gid in gap_ids:  # deterministic close order = open-gap order
            if gid in remaining and gid in closes:
                closed_order.append(gid)
                remaining.discard(gid)

    covered_weight = sum(weight_map[g] for g in closed_order)
    coverage_ratio = 1.0 if total_weight <= 0 else covered_weight / total_weight
    coverage_ratio = min(1.0, max(0.0, coverage_ratio))
    uncovered = [gid for gid in gap_ids if gid in remaining]

    return ClosurePlan(
        chosen=chosen,
        closed_gap_ids=closed_order,
        uncovered_gap_ids=uncovered,
        total_cost=total_cost,
        coverage_ratio=coverage_ratio,
    )
