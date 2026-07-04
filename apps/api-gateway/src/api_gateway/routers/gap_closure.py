"""Gap-closure planning endpoint — «minimal set of experiments» (§15.9/§23).

RU: Выводит наружу уже готовый жадный set-cover (`kg_retrievers.gap_closure_plan`):
из открытых пробелов графа собирает кандидатов-экспериментов и возвращает
минимальный набор («эти 3 эксперимента закроют 11 пробелов») — практичный,
зрелищный вывод для руководителя.

EN: Surfaces the ready greedy set-cover (`kg_retrievers.gap_closure_plan`): reads
open Gap nodes, assembles candidate experiments over them, and returns the
minimal covering set with an executive headline.

Modeling (no new schema): every Gap is attached to a subject via an ``ABOUT``
edge. A candidate *experiment* is a measurement campaign that would close a set
of gaps sharing a facet:

* **focused** — one subject (material/entity): closes every gap ``ABOUT`` it;
  cost ≈ number of distinct measurement kinds (gap types) it must produce.
* **campaign** — one domain: closes every gap whose subject sits in that domain;
  cost ≈ number of distinct subjects it must cover (broad but pricier).

Gap *weights* are the §15.9 priority scores, so the plan spends its budget on the
highest-value gaps first. Kuzu note (§14.8): custom props are not queryable
columns, so per-gap ``absence_confidence`` is read via ``get_node`` — but base
columns (``gap_type``/``domain``/``ABOUT`` target) are RETURNed directly, matching
the Neo4j server profile used by ``/gaps``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/gap-closure", tags=["gap-closure"])

# One aggregate read: every Gap + its ABOUT subject (base columns only, §14.8).
_GAPS_CYPHER = (
    "MATCH (g:Node) WHERE g.label='Gap' "
    "OPTIONAL MATCH (g)-[:Rel {type:'ABOUT'}]->(s:Node) "
    "RETURN g.id, coalesce(g.name,''), g.gap_type, g.domain, "
    "s.id, coalesce(s.name,''), s.domain "
    "LIMIT 2000"
)


def _norm(value: Any) -> str | None:
    """A non-empty trimmed string or ``None``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class _Gap:
    """One open gap enriched with subject + priority weight (§15.9)."""

    __slots__ = ("domain", "gap_type", "id", "name", "subject", "subject_id", "weight")

    def __init__(self, row: list[Any], store: Any) -> None:
        gid, gname, gtype, gdomain, sid, sname, sdomain = row
        self.id: str = gid
        self.name: str = gname or gid
        self.gap_type: str = _norm(gtype) or "unknown"
        # Prefer the gap's own domain, fall back to the subject's (§15.9).
        self.domain: str | None = _norm(gdomain) or _norm(sdomain)
        self.subject_id: str | None = _norm(sid)
        self.subject: str = _norm(sname) or self.subject_id or self.name
        self.weight: float = _gap_weight(self, store)


def _gap_weight(gap: _Gap, store: Any) -> float:
    """§15.9 priority score as the set-cover weight (absence_confidence via get_node)."""
    from kg_retrievers.gap_scoring import gap_priority_score

    ac = (store.get_node(gap.id) or {}).get("absence_confidence")
    return round(
        gap_priority_score(
            {
                "gap_type": gap.gap_type,
                "domain": gap.domain,
                "subject": gap.subject,
                "name": gap.name,
                "absence_confidence": ac,
            }
        ),
        4,
    )


def _load_gaps(store: Any, domain: str | None) -> list[_Gap]:
    gaps = [_Gap(r, store) for r in store.rows(_GAPS_CYPHER)]
    if domain:
        d = domain.lower()
        gaps = [g for g in gaps if (g.domain or "").lower() == d]
    return gaps


def _build_candidates(gaps: list[_Gap]) -> tuple[list[dict], dict[str, dict]]:
    """Assemble candidate experiments over the open gaps (focused + campaign tiers).

    Returns ``(candidates, meta)`` where ``candidates`` feed ``plan_closures`` and
    ``meta[experiment_id]`` carries the human-facing title/kind/facet for rendering.
    """
    focused: dict[str, list[_Gap]] = {}  # subject_id -> gaps ABOUT it
    campaign: dict[str, list[_Gap]] = {}  # domain -> gaps in it

    for g in gaps:
        key = g.subject_id or f"gaptype::{g.gap_type}"
        focused.setdefault(key, []).append(g)
        if g.domain:
            campaign.setdefault(g.domain, []).append(g)

    candidates: list[dict] = []
    meta: dict[str, dict] = {}

    for key, group in focused.items():
        exp_id = f"exp::focused::{key}"
        subject = group[0].subject
        # Effort ≈ number of distinct measurement kinds this campaign must produce.
        cost = float(len({g.gap_type for g in group}))
        candidates.append(
            {"experiment_id": exp_id, "closes": [g.id for g in group], "cost": max(cost, 1.0)}
        )
        meta[exp_id] = {
            "kind": "focused",
            "facet": subject,
            "title": f"Экспериментальная кампания по объекту «{subject}»",
            "detail": _gap_type_summary(group),
        }

    for dom, group in campaign.items():
        # Only worth offering a broad domain campaign when >1 subject is involved.
        subjects = {g.subject_id or g.subject for g in group}
        if len(subjects) < 2:
            continue
        exp_id = f"exp::campaign::{dom}"
        cost = float(len(subjects))
        candidates.append(
            {"experiment_id": exp_id, "closes": [g.id for g in group], "cost": max(cost, 1.0)}
        )
        meta[exp_id] = {
            "kind": "campaign",
            "facet": dom,
            "title": f"Сквозная кампания по области «{dom}»",
            "detail": f"{len(subjects)} объектов, {len(group)} пробелов",
        }

    return candidates, meta


def _gap_type_summary(group: list[_Gap]) -> str:
    """RU one-liner: gap-type histogram for a focused experiment card."""
    counts: dict[str, int] = {}
    for g in group:
        counts[g.gap_type] = counts.get(g.gap_type, 0) + 1
    parts = [f"{gt}×{n}" for gt, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return ", ".join(parts)


def _headline(n_exp: int, n_closed: int, n_total: int) -> str:
    """The executive one-liner (§15.9): «эти N экспериментов закроют M из K пробелов»."""
    if n_total == 0:
        return "Открытых пробелов нет — план не требуется."
    if n_exp == 0:
        return f"Пробелов: {n_total}. Подходящих экспериментов не найдено."
    return f"Эти {n_exp} эксперимент(а/ов) закроют {n_closed} из {n_total} пробелов."


@router.get("/plan")
def closure_plan(
    max_experiments: int | None = Query(default=None, ge=0),
    domain: str | None = None,
    budget: float | None = Query(default=None, gt=0),
) -> dict:
    """Minimal set of experiments that closes the most open gaps (§15.9/§23).

    ``max_experiments`` caps the plan size (``None`` = until nothing new is covered);
    ``domain`` restricts the scope; ``budget`` caps total cost (post-filter on the
    greedy order). Returns the chosen experiments (each with the gaps it closes),
    the still-open gaps, a coverage summary and an executive headline.
    """
    from kg_retrievers.gap_closure_plan import plan_closures

    store = get_store()
    gaps = _load_gaps(store, domain)
    by_id = {g.id: g for g in gaps}
    weights = {g.id: g.weight for g in gaps}

    candidates, meta = _build_candidates(gaps)
    plan = plan_closures(
        [{"gap_id": g.id, "weight": g.weight} for g in gaps],
        candidates,
        weights=weights,
        max_experiments=max_experiments,
    )

    # Rebuild per-experiment gap lists from the plan's selection order, honouring
    # the optional cost budget (drop trailing experiments that overflow it).
    remaining = {g.id for g in gaps}
    closes_by = {c["experiment_id"]: set(c["closes"]) for c in candidates}
    cost_by = {c["experiment_id"]: c["cost"] for c in candidates}
    experiments: list[dict] = []
    running_cost = 0.0
    for exp_id in plan.chosen:
        cost = float(cost_by.get(exp_id, 1.0))
        if budget is not None and running_cost + cost > budget:
            continue
        closes = closes_by.get(exp_id, set())
        newly = [gid for gid in plan.closed_gap_ids if gid in remaining and gid in closes]
        if not newly:
            continue
        for gid in newly:
            remaining.discard(gid)
        running_cost += cost
        m = meta.get(exp_id, {})
        experiments.append(
            {
                "experiment_id": exp_id,
                "kind": m.get("kind"),
                "title": m.get("title", exp_id),
                "facet": m.get("facet"),
                "detail": m.get("detail"),
                "cost": cost,
                "n_gaps_closed": len(newly),
                "gaps": [_gap_card(by_id[gid]) for gid in newly if gid in by_id],
            }
        )

    n_total = len(gaps)
    n_closed = n_total - len(remaining)
    coverage = round(n_closed / n_total, 4) if n_total else 1.0
    uncovered = sorted(
        (by_id[gid] for gid in remaining), key=lambda g: g.weight, reverse=True
    )
    return {
        "headline": _headline(len(experiments), n_closed, n_total),
        "summary": {
            "n_experiments": len(experiments),
            "n_gaps_total": n_total,
            "n_gaps_closed": n_closed,
            "n_gaps_uncovered": len(remaining),
            "coverage_ratio": coverage,
            "weighted_coverage_ratio": plan.coverage_ratio,
            "total_cost": round(running_cost, 4),
        },
        "experiments": experiments,
        "uncovered": [_gap_card(g) for g in uncovered],
    }


def _gap_card(g: _Gap) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "gap_type": g.gap_type,
        "domain": g.domain,
        "subject": g.subject,
        "weight": g.weight,
    }


@router.get("/candidates")
def list_candidates(domain: str | None = None) -> dict:
    """The raw candidate experiments (transparency into what the plan chooses from)."""
    store = get_store()
    gaps = _load_gaps(store, domain)
    candidates, meta = _build_candidates(gaps)
    fields = ("kind", "title", "facet", "detail")
    items = [
        {
            "experiment_id": c["experiment_id"],
            "cost": c["cost"],
            "n_closes": len(c["closes"]),
            **{k: meta.get(c["experiment_id"], {}).get(k) for k in fields},
        }
        for c in sorted(candidates, key=lambda c: (-len(c["closes"]), c["cost"]))
    ]
    return {"count": len(items), "n_gaps": len(gaps), "candidates": items}
