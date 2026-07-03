"""Compose ``depends_on`` validation — проверка графа зависимостей (§2.4).

Docker-Compose lets a service declare ``depends_on: {other: {condition: ...}}``.
For a healthy startup ordering we want three guarantees, which this module
turns into one frozen, JSON-serialisable verdict:

* **missing_targets** — a service depends on a name that is *not itself* a
  declared service («висячая цель»); such an edge can never be satisfied.
* **weak_conditions** — a dependency whose ``condition`` is anything other than
  ``'service_healthy'`` («слабое условие»); surfaced as a warning but does
  *not* fail ``ok`` — a started-but-unhealthy target may still be acceptable.
* **cycles** — any dependency cycle reachable over the ``depends_on`` edges,
  found by DFS; a self-loop counts as a cycle.

``ok`` is ``True`` exactly when there are no cycles and no missing targets.
Everything is deterministic and side-effect free: all tuple fields are sorted.

Public API:

* :class:`DependencyReport` — frozen verdict with :meth:`DependencyReport.as_dict`.
* :func:`check_dependencies` — build the report from a ``deps`` mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "DependencyReport",
    "check_dependencies",
]

HEALTHY = "service_healthy"

_WHITE, _GREY, _BLACK = 0, 1, 2


@dataclass(frozen=True, slots=True)
class DependencyReport:
    """Immutable ``depends_on`` verdict — результат проверки (§2.4).

    ``ok`` is ``True`` exactly when both ``cycles`` and ``missing_targets`` are
    empty; ``weak_conditions`` are informational only. All tuple fields are
    sorted so the record is a pure function of the input mapping.
    """

    cycles: tuple[tuple[str, ...], ...]
    missing_targets: tuple[tuple[str, str], ...]
    weak_conditions: tuple[tuple[str, str], ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — сводка как словарь (§2.4)."""
        return {
            "cycles": [list(cycle) for cycle in self.cycles],
            "missing_targets": [list(pair) for pair in self.missing_targets],
            "weak_conditions": [list(pair) for pair in self.weak_conditions],
            "ok": self.ok,
        }


def _find_cycles(edges: Mapping[str, Mapping[str, str]]) -> tuple[tuple[str, ...], ...]:
    """DFS over ``depends_on`` edges — поиск циклов (§2.4).

    Returns each distinct cycle once, as the tuple of nodes on the cycle
    rotated so the lexicographically smallest node comes first. A self-loop
    ``a -> a`` yields ``('a',)``.
    """
    color: dict[str, int] = dict.fromkeys(edges, _WHITE)
    found: set[tuple[str, ...]] = set()

    def canonical(cycle: list[str]) -> tuple[str, ...]:
        pivot = min(range(len(cycle)), key=lambda i: cycle[i])
        return tuple(cycle[pivot:] + cycle[:pivot])

    def visit(node: str, stack: list[str]) -> None:
        color[node] = _GREY
        stack.append(node)
        for target in edges.get(node, {}):
            if target not in color:  # missing target — no node to recurse into
                continue
            if color[target] == _GREY:
                idx = stack.index(target)
                found.add(canonical(stack[idx:]))
            elif color[target] == _WHITE:
                visit(target, stack)
        stack.pop()
        color[node] = _BLACK

    for node in edges:
        if color[node] == _WHITE:
            visit(node, [])

    return tuple(sorted(found))


def check_dependencies(deps: Mapping[str, Mapping[str, str]]) -> DependencyReport:
    """Validate a compose ``depends_on`` graph — проверить граф (§2.4).

    ``deps`` maps ``service -> {dependency: condition}``. Reports missing
    targets, weak conditions and cycles; ``ok`` iff no cycles and no missing
    targets.
    """
    services = set(deps)
    missing: list[tuple[str, str]] = []
    weak: list[tuple[str, str]] = []

    for service in deps:
        for dependency, condition in deps[service].items():
            if dependency not in services:
                missing.append((service, dependency))
            if condition != HEALTHY:
                weak.append((service, dependency))

    cycles = _find_cycles(deps)
    missing_targets = tuple(sorted(missing))
    weak_conditions = tuple(sorted(weak))
    ok = not cycles and not missing_targets
    return DependencyReport(
        cycles=cycles,
        missing_targets=missing_targets,
        weak_conditions=weak_conditions,
        ok=ok,
    )
