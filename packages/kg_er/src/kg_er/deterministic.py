"""Deterministic small-N entity resolution (§8.5).

Splink's EM parameter estimation needs many records to converge; the real
per-document ER call resolves a handful of mentions at a time, where EM defaults
over-merge. For inputs below :data:`SPLINK_MIN_ROWS` we score pairs with
transparent, deterministic rules over the same feature columns
(:mod:`kg_er.features`) and aggregate with the same union-find as the Splink
path, so results feed the identical decision engine (§8.7) and are reproducible
in CI.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rapidfuzz.distance import JaroWinkler

from kg_er.comparisons.text import token_set
from kg_er.models.base import ClusterResult, _union_find

# Below this many rows, EM cannot train reliably — use deterministic scoring.
SPLINK_MIN_ROWS = 50


def _name_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return JaroWinkler.similarity(a, b)


def _eq(a: Any, b: Any) -> bool:
    return bool(a) and bool(b) and a == b


def _material_score(x: dict, y: dict) -> float:
    # Hard precision guard: two materials with known, different element sets are
    # different entities (copper Cu vs Al-Cu-Mg) regardless of name similarity.
    ek_x, ek_y = x.get("element_key", ""), y.get("element_key", "")
    if ek_x and ek_y and ek_x != ek_y:
        return 0.1
    if _eq(x.get("normalized_formula"), y.get("normalized_formula")):
        return 0.97
    name = _name_sim(x.get("name_clean", ""), y.get("name_clean", ""))
    if _eq(ek_x, ek_y):
        return max(0.9, name)
    if _eq(x.get("designation_code"), y.get("designation_code")):
        return max(0.88, name)
    return name if name >= 0.9 else min(name, 0.45)


def _person_score(x: dict, y: dict) -> float:
    if _eq(x.get("orcid"), y.get("orcid")):
        return 0.99
    fam = _eq(x.get("family_name"), y.get("family_name"))
    if not fam:
        return min(_name_sim(x.get("name_clean", ""), y.get("name_clean", "")), 0.4)
    ini = _eq(x.get("given_initial"), y.get("given_initial"))
    dom = _eq(x.get("email_domain"), y.get("email_domain"))
    base = 0.9 if ini else 0.6
    return min(0.98, base + (0.06 if dom else 0.0))


def _equipment_score(x: dict, y: dict) -> float:
    if _eq(x.get("manufacturer"), y.get("manufacturer")) and _eq(
        x.get("model_code"), y.get("model_code")
    ):
        return 0.96
    name = _name_sim(x.get("name_clean", ""), y.get("name_clean", ""))
    if _eq(x.get("model_code"), y.get("model_code")):
        return max(0.85, name)
    return name if name >= 0.9 else min(name, 0.45)


def _lab_score(x: dict, y: dict) -> float:
    org = _name_sim(x.get("org", ""), y.get("org", ""))
    same_place = _eq(x.get("city"), y.get("city")) or _eq(x.get("country"), y.get("country"))
    tx, ty = token_set(x.get("org")), token_set(y.get("org"))
    # one org-name is an abbreviation/subset of the other (e.g. "НИТУ МИСИС" ⊃ "МИСИС")
    subset = bool(tx) and bool(ty) and (tx <= ty or ty <= tx)
    if (_eq(x.get("org_token"), y.get("org_token")) or subset) and same_place:
        return max(0.9, org)
    if org >= 0.92:
        return org
    return min(org, 0.45)


_SCORERS = {
    "Material": _material_score,
    "Alloy": _material_score,
    "Equipment": _equipment_score,
    "Person": _person_score,
    "Lab": _lab_score,
    "ResearchTeam": _lab_score,
}


def pair_score(entity_type: str, x: dict, y: dict) -> float:
    """Deterministic match probability in [0, 1] for two feature rows."""
    return _SCORERS.get(entity_type, _material_score)(x, y)


def deterministic_clusters(
    entity_type: str, rows: Sequence[dict], *, threshold: float = 0.5
) -> list[ClusterResult]:
    """Score all pairs, keep those ≥ threshold, aggregate into transitive clusters."""
    pairs: list[tuple[str, str]] = []
    pair_prob: dict[tuple[str, str], float] = {}
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = str(rows[i]["unique_id"]), str(rows[j]["unique_id"])
            p = pair_score(entity_type, rows[i], rows[j])
            if p >= threshold:
                key = (a, b) if a <= b else (b, a)
                pairs.append(key)
                pair_prob[key] = p

    parent = _union_find(pairs)
    groups: dict[str, set[str]] = {}
    # ensure singletons are represented so callers see every input id
    for r in rows:
        uid = str(r["unique_id"])
        parent.setdefault(uid, uid)
    for node in parent:
        root = node
        while parent[root] != root:
            root = parent[root]
        groups.setdefault(root, set()).add(node)

    clusters: list[ClusterResult] = []
    for members in groups.values():
        member_tuple = tuple(sorted(members))
        rel = {k: v for k, v in pair_prob.items() if k[0] in members and k[1] in members}
        clusters.append(
            ClusterResult(
                members=member_tuple,
                max_probability=max(rel.values()) if rel else 0.0,
                pair_probabilities=rel,
            )
        )
    return clusters
