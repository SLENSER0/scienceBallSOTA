"""§12.10 — static Cypher cost/complexity estimator for the Text2Cypher cost guard.

The graph-service :mod:`graph_service.cypher_guard` hardens the *read path*
(read-only keyword scan, label/relationship allowlist, ``LIMIT`` enforcement) but
does **no** cost or cartesian-product analysis: a syntactically valid, read-only
query can still be ruinously expensive (deep variable-length traversals, cross
products of disconnected patterns). This module is the missing §12.10 cost-guard
step — a *static* estimator that never touches the graph.

Стоимость оценивается статически (без обращения к графу) по трём сигналам:

- **match_count** — сколько ``MATCH`` предложений (строковые литералы вырезаются
  первыми, поэтому слово ``MATCH`` внутри значения — это данные, а не clause);
- **var_length_hops** — наибольшая верхняя граница из шаблонов ``[*a..b]``;
- **has_cartesian** — декартово произведение: одно ``MATCH`` перечисляет
  несвязанные (не разделяющие переменную) шаблоны через запятую, ЛИБО более
  позднее ``MATCH`` не делит ни одной переменной с предыдущими.

    estimated_cost = base_per_match * match_count
                     * (var_length_hops or 1) * (10 if has_cartesian else 1)

A query is ``blocked`` when it forms a cartesian product **or** its estimated
cost exceeds ``max_cost``; ``reason`` explains why (``None`` when allowed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# -- defaults --------------------------------------------------------------
DEFAULT_MAX_COST = 10000  # оценочная стоимость выше этого -> blocked
DEFAULT_BASE_PER_MATCH = 100  # базовая цена одного MATCH предложения
CARTESIAN_MULTIPLIER = 10  # штраф за декартово произведение

# -- clause / pattern lexemes ----------------------------------------------
# Keywords that terminate a MATCH pattern (start of the next clause).
_CLAUSE_KW = re.compile(
    r"\b(OPTIONAL\s+MATCH|MATCH|WHERE|RETURN|WITH|UNWIND|CALL|CREATE|MERGE|SET"
    r"|DELETE|REMOVE|ORDER\s+BY|SKIP|LIMIT|UNION|FOREACH)\b",
    re.IGNORECASE,
)
_MATCH_KW = re.compile(r"\bMATCH\b", re.IGNORECASE)
# Variable right after ``(`` (node) or ``[`` (relationship); anon/anchor -> no group.
_NODE_VAR = re.compile(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)")
_REL_VAR = re.compile(r"\[\s*([A-Za-z_][A-Za-z0-9_]*)")
# Variable-length bound: ``[*a..b]`` / ``[*..b]`` / ``[*a]`` / ``[*]``.
_VAR_LEN = re.compile(r"\[\s*[A-Za-z0-9_]*\s*\*\s*(\d*)\s*(?:\.\.\s*(\d*))?\s*\]")


@dataclass(frozen=True)
class CostEstimate:
    """Static §12.10 cost verdict for one Cypher query.

    ``estimated_cost`` is the product of ``base_per_match``, ``match_count``,
    ``var_length_hops or 1`` and the cartesian penalty. ``blocked`` is True when
    the query is a cartesian product or exceeds ``max_cost``; ``reason`` is a
    short human-readable cause (``None`` iff allowed).
    """

    match_count: int
    var_length_hops: int
    has_cartesian: bool
    estimated_cost: int
    blocked: bool
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "match_count": self.match_count,
            "var_length_hops": self.var_length_hops,
            "has_cartesian": self.has_cartesian,
            "estimated_cost": self.estimated_cost,
            "blocked": self.blocked,
            "reason": self.reason,
        }


def _strip_literals(cypher: str) -> str:
    """Blank single/double-quoted strings and backtick identifiers (§12.10).

    So a keyword or comma inside a *value* (``name = 'MATCH x'``) is data, not a
    clause — it must not inflate ``match_count`` or the pattern parse.
    """
    out = re.sub(r"'(?:\\.|[^'\\])*'", "''", cypher)
    out = re.sub(r'"(?:\\.|[^"\\])*"', '""', out)
    return re.sub(r"`(?:[^`])*`", "``", out)


def _match_clauses(scrubbed: str) -> list[str]:
    """Return the pattern body of every ``MATCH`` clause (literals pre-stripped).

    Each body spans from a ``MATCH`` keyword to the next clause keyword, so the
    ``WHERE`` / ``RETURN`` tail is excluded from the pattern analysis.
    """
    bounds = [(m.start(), m.end(), m.group(0)) for m in _CLAUSE_KW.finditer(scrubbed)]
    clauses: list[str] = []
    for i, (_start, end, kw) in enumerate(bounds):
        if kw.upper().replace("OPTIONAL", "").strip() != "MATCH":
            continue
        nxt = bounds[i + 1][0] if i + 1 < len(bounds) else len(scrubbed)
        clauses.append(scrubbed[end:nxt])
    return clauses


def _split_top_level(pattern: str) -> list[str]:
    """Split a MATCH body on commas that sit outside ``()``/``[]``/``{}``.

    Commas inside a map ``{a: 1, b: 2}`` or a bound stay with their pattern part.
    """
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in pattern:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in parts if p.strip()]


def _vars_in(fragment: str) -> set[str]:
    """Named node + relationship variables in a pattern fragment (anon -> none)."""
    return set(_NODE_VAR.findall(fragment)) | set(_REL_VAR.findall(fragment))


def _component_count(var_sets: list[set[str]]) -> int:
    """Number of connected components over parts linked by a shared variable.

    Union-find: two comma-separated parts are joined when they share any named
    variable. ``> 1`` component means the parts do not connect -> cartesian.
    """
    n = len(var_sets)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if var_sets[i] & var_sets[j]:
                parent[find(i)] = find(j)
    return len({find(i) for i in range(n)})


def _detect_cartesian(clauses: list[str]) -> bool:
    """Flag a cartesian product across/within the query's MATCH clauses (§12.10)."""
    earlier: set[str] = set()
    found = False
    for idx, clause in enumerate(clauses):
        parts = _split_top_level(clause)
        var_sets = [_vars_in(p) for p in parts]
        if var_sets and _component_count(var_sets) > 1:
            found = True
        clause_vars: set[str] = set().union(*var_sets) if var_sets else set()
        if idx > 0 and earlier and clause_vars and earlier.isdisjoint(clause_vars):
            found = True
        earlier |= clause_vars
    return found


def _max_var_length(scrubbed: str) -> int:
    """Largest variable-length upper bound over all ``[*a..b]`` patterns (0 if none)."""
    best = 0
    for lower, upper in _VAR_LEN.findall(scrubbed):
        if upper:
            best = max(best, int(upper))
        elif lower:
            best = max(best, int(lower))
    return best


def estimate_cost(
    cypher: str,
    *,
    max_cost: int = DEFAULT_MAX_COST,
    base_per_match: int = DEFAULT_BASE_PER_MATCH,
) -> CostEstimate:
    """Statically estimate a Cypher query's cost and decide the §12.10 cost guard.

    Строковые литералы вырезаются первыми, затем считаются ``MATCH`` предложения,
    извлекается максимальная граница ``[*a..b]`` и проверяется декартово
    произведение. Query is blocked on a cartesian product or on cost > ``max_cost``.
    """
    scrubbed = _strip_literals(cypher)
    match_count = len(_MATCH_KW.findall(scrubbed))
    var_length_hops = _max_var_length(scrubbed)
    has_cartesian = _detect_cartesian(_match_clauses(scrubbed))

    estimated_cost = (
        base_per_match
        * match_count
        * (var_length_hops or 1)
        * (CARTESIAN_MULTIPLIER if has_cartesian else 1)
    )

    reason: str | None = None
    if has_cartesian:
        reason = "cartesian product across disconnected patterns"
    elif estimated_cost > max_cost:
        reason = f"estimated cost {estimated_cost} exceeds max_cost {max_cost}"
    blocked = reason is not None

    return CostEstimate(
        match_count=match_count,
        var_length_hops=var_length_hops,
        has_cartesian=has_cartesian,
        estimated_cost=estimated_cost,
        blocked=blocked,
        reason=reason,
    )
