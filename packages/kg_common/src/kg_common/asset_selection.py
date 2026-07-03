"""Asset-selection syntax resolution — выбор подмножеств ассетов (§9.2).

Pure-python re-implementation of the *asset-selection* mini-language that
``define_asset_job`` accepts in orchestrators such as Dagster, **without taking
a dependency on Dagster** (§9.2). A *query* is a comma-separated list of tokens;
each token names a base asset key and, via ``+``/``*`` sigils, asks to pull in
that key's neighbourhood in the dependency graph:

* a leading sigil selects **upstream** (dependencies) — ``+key`` one hop,
  ``++key`` two hops, ``*key`` the whole upstream closure;
* a trailing sigil selects **downstream** (dependents) — ``key+`` one hop,
  ``key++`` two hops, ``key*`` the whole downstream closure.

Resolution walks a plain dependency :class:`~collections.abc.Mapping`
``deps`` that maps every key to *its own upstream dependencies* (the same shape
:class:`kg_common.asset_graph.Asset` uses). Downstream edges are derived by
inverting that map, so no separate graph object is required — «граф выводится из
словаря зависимостей». The expanded keys are de-duplicated preserving
insertion order (base first, then upstream, then downstream), which keeps
dependencies ahead of dependents in the common cases (§9.2 «детерминизм»).

Public API:

* :func:`parse_token` — split one token into ``(base, up_hops, down_hops)``.
* :func:`resolve`     — expand a whole query into a :class:`SelectionResult`.
* :class:`SelectionResult` — frozen ``(query, keys)`` record with ``as_dict``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "SelectionResult",
    "parse_token",
    "resolve",
]

# Sigil characters that steer traversal — символы обхода графа (§9.2).
_SIGILS = "+*"
# Unbounded traversal marker used for ``*`` — безграничный обход (§9.2).
_UNBOUNDED = -1


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Immutable outcome of resolving a selection query — результат выбора (§9.2).

    ``query`` is the raw selection string as supplied; ``keys`` are the resolved
    asset keys in insertion order, already de-duplicated. The record is a plain
    frozen value so it can be hashed, compared and serialized.
    """

    query: str
    keys: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — «запрос + список ключей» (§9.2).

        ``keys`` is rendered as a ``list`` so the result round-trips through JSON.
        """
        return {"query": self.query, "keys": list(self.keys)}


def parse_token(token: str) -> tuple[str, int, int]:
    """Split one selection token into ``(base, up_hops, down_hops)`` — токен (§9.2).

    Leading sigils select upstream hops, trailing sigils select downstream hops.
    A run of ``+`` counts hops (``++`` → 2); a ``*`` anywhere in that run means the
    whole closure and is reported as ``-1``. Examples::

        parse_token("graph_upsert+")  == ("graph_upsert", 0, 1)
        parse_token("+graph_upsert")  == ("graph_upsert", 1, 0)
        parse_token("*qdrant_index")  == ("qdrant_index", -1, 0)

    Raises :class:`ValueError` if the token is blank or has no base key.
    """
    text = token.strip()
    if not text:
        raise ValueError("empty selection token")

    start = 0
    up_star = False
    up_plus = 0
    while start < len(text) and text[start] in _SIGILS:
        if text[start] == "*":
            up_star = True
        else:
            up_plus += 1
        start += 1

    end = len(text)
    down_star = False
    down_plus = 0
    while end > start and text[end - 1] in _SIGILS:
        if text[end - 1] == "*":
            down_star = True
        else:
            down_plus += 1
        end -= 1

    base = text[start:end]
    if not base:
        raise ValueError(f"selection token has no base key: {token!r}")

    up_hops = _UNBOUNDED if up_star else up_plus
    down_hops = _UNBOUNDED if down_star else down_plus
    return (base, up_hops, down_hops)


def _walk(start: str, adjacency: Mapping[str, Sequence[str]], hops: int) -> list[str]:
    """BFS from ``start`` over ``adjacency`` up to ``hops`` levels — обход (§9.2).

    ``hops`` of ``-1`` means unbounded. The starting node is excluded from the
    result; newly discovered nodes at each level are visited in sorted order so
    the traversal is a pure function of the graph.
    """
    if hops == 0:
        return []
    seen: set[str] = {start}
    order: list[str] = []
    frontier: list[str] = [start]
    level = 0
    while frontier and (hops < 0 or level < hops):
        nxt: list[str] = []
        for node in frontier:
            for neigh in adjacency.get(node, ()):
                if neigh not in seen:
                    seen.add(neigh)
                    order.append(neigh)
                    nxt.append(neigh)
        frontier = sorted(nxt)
        level += 1
    return order


def _universe(deps: Mapping[str, Sequence[str]]) -> set[str]:
    """All keys mentioned as a node or a dependency — вселенная ключей (§9.2)."""
    known: set[str] = set(deps)
    for upstream in deps.values():
        known.update(upstream)
    return known


def _downstream(deps: Mapping[str, Sequence[str]], universe: set[str]) -> dict[str, list[str]]:
    """Invert ``deps`` into direct-dependents edges — прямые потомки (§9.2)."""
    down: dict[str, list[str]] = {key: [] for key in universe}
    for key, upstream in deps.items():
        for dep in upstream:
            down.setdefault(dep, []).append(key)
    return down


def resolve(query: str, deps: Mapping[str, Sequence[str]]) -> SelectionResult:
    """Expand a selection ``query`` over ``deps`` — разрешение запроса (§9.2).

    ``deps`` maps every key to *its own upstream dependencies*. The query is split
    on commas; each token is parsed by :func:`parse_token` and expanded to its base
    key plus the requested upstream and downstream neighbourhood. Results are
    de-duplicated preserving first-seen order (base, then upstream, then
    downstream). An unknown base key raises :class:`KeyError`.
    """
    universe = _universe(deps)
    downstream = _downstream(deps, universe)

    keys: list[str] = []
    seen: set[str] = set()
    for raw in query.split(","):
        token = raw.strip()
        if not token:
            continue
        base, up_hops, down_hops = parse_token(token)
        if base not in universe:
            raise KeyError(base)
        expanded = [base]
        expanded.extend(_walk(base, deps, up_hops))
        expanded.extend(_walk(base, downstream, down_hops))
        for key in expanded:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return SelectionResult(query=query, keys=tuple(keys))
