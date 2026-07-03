"""Technology-solution ranking over the knowledge graph (§24.21).

Ранжирование технологических решений (*technology solutions*) — упорядочивает
``TechnologySolution`` узлы по совокупной обоснованности: объём подтверждающего
эвиденса, доля проверенного (verified) эвиденса и свежесть данных (recency).

English: :func:`rank_solutions` walks every ``TechnologySolution`` (optionally scoped
to one ``domain``), counts its linked evidence / measurements, counts how many of
those are verified, derives a recency factor from the most recent year seen (solution
or its evidence), and blends the three into a single score::

    score = EVIDENCE_WEIGHT      * evidence_count
          + VERIFICATION_WEIGHT  * verified_count
          + RECENCY_WEIGHT       * recency_factor

Solutions come back sorted by descending score (``solution_id`` breaks ties), capped
to the ``top`` best. An empty graph — or a ``domain`` present nowhere — yields ``[]``.

Kuzu note: custom node props are NOT queryable columns, so the neighbour walk RETURNs
only base ``Node`` columns (``id`` / ``label`` / ``verified`` / ``verification_level`` /
``year``); the solution's own name / domain / year are read via base columns too. The
module is read-only: it never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Node label of a technology solution being ranked (§24.2 / §24.21).
SOLUTION_LABEL = "TechnologySolution"

# Labels that count as supporting evidence for a solution (§24.21).
EVIDENCE_LABELS: frozenset[str] = frozenset(
    {"Evidence", "Paper", "Document", "Measurement", "TechnoEconomicIndicator", "Observation"}
)

# ``verification_level`` values (normalised) that mark an evidence node as verified.
VERIFIED_LEVELS: frozenset[str] = frozenset({"verified", "confirmed", "validated", "reproduced"})

# Score weights (§24.21): verified evidence outweighs raw evidence; recency is a tie-shaper.
EVIDENCE_WEIGHT = 1.0
VERIFICATION_WEIGHT = 2.0
RECENCY_WEIGHT = 1.0

# Recency ramp: ``year`` <= floor scores 0.0, >= ceil scores 1.0, linear in between (§24.21).
RECENCY_FLOOR_YEAR = 2000
RECENCY_CEIL_YEAR = 2025

# Score rounding — keeps ``as_dict()`` output stable and free of float noise.
SCORE_NDIGITS = 6

# Default number of top-ranked solutions returned.
DEFAULT_TOP = 10


@dataclass(frozen=True)
class RankedSolution:
    """One ranked technology solution (§24.21).

    ``score`` blends evidence volume, verification and recency; ``evidence_count`` is the
    number of linked evidence / measurement nodes; ``verified_count`` is how many of those
    are verified (``verified`` flag or a strong ``verification_level``).
    """

    solution_id: str
    name: str
    score: float
    evidence_count: int
    verified_count: int

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{solution_id, name, score, evidence_count, verified_count}``."""
        return {
            "solution_id": self.solution_id,
            "name": self.name,
            "score": self.score,
            "evidence_count": self.evidence_count,
            "verified_count": self.verified_count,
        }


def _norm(value: object) -> str:
    """Normalise a string value: lower-cased and stripped (else ``""`` for non-strings)."""
    return value.strip().lower() if isinstance(value, str) else ""


def _is_verified(node: dict[str, Any]) -> bool:
    """True if an evidence node is verified — the ``verified`` flag or a strong level."""
    if node.get("verified") is True:
        return True
    return _norm(node.get("verification_level")) in VERIFIED_LEVELS


def _as_year(value: object) -> int | None:
    """Coerce a raw ``year`` cell to ``int`` (``None`` when absent / non-numeric)."""
    if isinstance(value, bool):  # bool is an int subclass — never a year
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _recency_factor(years: list[int]) -> float:
    """Recency in ``[0, 1]`` from the most recent year (empty -> ``0.0``) (§24.21)."""
    if not years:
        return 0.0
    year = max(years)
    span = RECENCY_CEIL_YEAR - RECENCY_FLOOR_YEAR
    ramp = (year - RECENCY_FLOOR_YEAR) / span
    return max(0.0, min(1.0, ramp))


def _solution_rows(store: KuzuGraphStore, domain: str | None) -> list[tuple[str, str, int | None]]:
    """All in-scope ``TechnologySolution`` rows as ``(id, name, year)`` (base columns).

    ``name`` falls back to ``canonical_name`` then ``id``; the result is ordered by ``id``
    for deterministic ranking of tied scores.
    """
    cypher = "MATCH (s:Node) WHERE s.label=$label "
    params: dict[str, Any] = {"label": SOLUTION_LABEL}
    if domain is not None:
        cypher += "AND s.domain=$domain "
        params["domain"] = domain
    cypher += "RETURN s.id, s.name, s.canonical_name, s.year ORDER BY s.id"
    out: list[tuple[str, str, int | None]] = []
    for sid, name, canonical, year in store.rows(cypher, params):
        display = name if isinstance(name, str) and name else canonical
        display = display if isinstance(display, str) and display else sid
        out.append((sid, display, _as_year(year)))
    return out


def _linked_evidence(store: KuzuGraphStore, solution_id: str) -> list[dict[str, Any]]:
    """Distinct evidence / measurement nodes linked to a solution, as base-column dicts.

    Both edge directions are walked; DISTINCT plus a Python de-dup on ``id`` guard against
    a node reached through several relations being counted twice. Only ``Node`` base columns
    are RETURNed (custom props are not queryable in Kuzu).
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[r:Rel]-(m:Node) "
        "RETURN DISTINCT m.id, m.label, m.verified, m.verification_level, m.year",
        {"sid": solution_id},
    )
    seen: dict[str, dict[str, Any]] = {}
    for mid, label, verified, level, year in rows:
        if mid in seen or label not in EVIDENCE_LABELS:
            continue
        seen[mid] = {
            "id": mid,
            "label": label,
            "verified": verified,
            "verification_level": level,
            "year": year,
        }
    return list(seen.values())


def _score_solution(
    solution_id: str, name: str, solution_year: int | None, store: KuzuGraphStore
) -> RankedSolution:
    """Score one solution from its linked evidence, verification and recency (§24.21)."""
    linked = _linked_evidence(store, solution_id)
    evidence_count = len(linked)
    verified_count = sum(1 for node in linked if _is_verified(node))

    years = [y for y in (_as_year(n.get("year")) for n in linked) if y is not None]
    if solution_year is not None:
        years.append(solution_year)
    recency = _recency_factor(years)

    score = (
        EVIDENCE_WEIGHT * evidence_count
        + VERIFICATION_WEIGHT * verified_count
        + RECENCY_WEIGHT * recency
    )
    return RankedSolution(
        solution_id=solution_id,
        name=name,
        score=round(score, SCORE_NDIGITS),
        evidence_count=evidence_count,
        verified_count=verified_count,
    )


def rank_solutions(
    store: KuzuGraphStore, *, domain: str | None = None, top: int = DEFAULT_TOP
) -> list[RankedSolution]:
    """Rank technology solutions over ``store`` by evidence, verification and recency (§24.21).

    Walks every ``TechnologySolution`` (optionally scoped to ``domain``), scoring each by
    the volume of linked evidence, how much of it is verified, and how recent it is. Results
    come back sorted by descending score, with ``solution_id`` breaking ties for a stable
    order, and capped to the ``top`` best (``top=None`` returns all; ``top<=0`` returns
    ``[]``). An empty graph — or a ``domain`` present nowhere — yields ``[]`` (graceful).
    """
    ranked = [
        _score_solution(sid, name, year, store) for sid, name, year in _solution_rows(store, domain)
    ]
    ranked.sort(key=lambda r: (-r.score, r.solution_id))
    if top is not None:
        ranked = ranked[: max(0, top)]
    return ranked
