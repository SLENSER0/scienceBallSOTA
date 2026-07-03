"""Endpoint -> permission fail-closed coverage (§19.1 authz coverage).

Every HTTP route the API exposes must map to exactly one required permission
scope, or be an *explicitly* public route. Anything else is a coverage
violation and is treated as **denied by default** («запрет по умолчанию»).

The static route table :data:`ENDPOINT_RULES` pairs a ``(method, path)`` with
the permission scope a caller needs (e.g. ``documents:upload``).
:data:`PUBLIC_ROUTES` names the ``path`` values that are intentionally open
(health, login, docs). :func:`required_permission` resolves the scope for a
route (``None`` for public, ``KeyError``-free), and :func:`audit_coverage`
classifies a set of live routes into *mapped* / *public* / *unmapped* so a
test or CI gate can fail closed when a new endpoint ships without an authz
rule («новый маршрут без правила — нарушение»).

Pure-python, no third-party dependency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EndpointRule:
    """One route bound to the permission scope it requires («правило маршрута»)."""

    method: str
    path: str
    permission: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict («в словарь»)."""
        return {"method": self.method, "path": self.path, "permission": self.permission}


# Static authz table: each mutating / read route maps to a required scope.
# «Таблица маршрут -> право»: fail-closed reference for the whole API surface.
ENDPOINT_RULES: tuple[EndpointRule, ...] = (
    EndpointRule("POST", "/documents", "documents:upload"),
    EndpointRule("GET", "/documents", "documents:read"),
    EndpointRule("DELETE", "/documents/{doc_id}", "documents:delete"),
    EndpointRule("POST", "/documents/{doc_id}/reprocess", "documents:reprocess"),
    EndpointRule("GET", "/graph/nodes/{node_id}", "graph:read"),
    EndpointRule("POST", "/graph/query", "graph:query"),
    EndpointRule("POST", "/chat", "chat:invoke"),
    EndpointRule("GET", "/chat/sessions", "chat:read"),
    EndpointRule("POST", "/admin/reindex", "admin:reindex"),
    EndpointRule("GET", "/admin/users", "admin:users:read"),
)

# Intentionally unauthenticated routes («явно публичные маршруты»).
PUBLIC_ROUTES: frozenset[str] = frozenset(
    {
        "/health",
        "/readyz",
        "/auth/login",
        "/auth/refresh",
        "/docs",
        "/openapi.json",
    }
)

# Fast lookup index: (method, path) -> permission scope.
_RULE_INDEX: dict[tuple[str, str], str] = {
    (rule.method, rule.path): rule.permission for rule in ENDPOINT_RULES
}


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Fail-closed classification of live routes («отчёт покрытия»).

    * ``mapped`` — routes with an explicit :class:`EndpointRule`.
    * ``public`` — routes whose ``path`` is in :data:`PUBLIC_ROUTES`.
    * ``unmapped`` — everything else: a coverage violation («нарушение»).
    """

    mapped: tuple[EndpointRule, ...]
    public: tuple[tuple[str, str], ...]
    unmapped: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict with list-typed sections («в словарь»)."""
        return {
            "mapped": [rule.as_dict() for rule in self.mapped],
            "public": [list(route) for route in self.public],
            "unmapped": [list(route) for route in self.unmapped],
        }


def required_permission(method: str, path: str) -> str | None:
    """Return the scope required for ``(method, path)``.

    ``None`` when ``path`` is an explicit public route. Lookup is
    ``KeyError``-free: unknown routes also return ``None`` here, but they are
    surfaced as violations by :func:`audit_coverage` («без исключений»).
    """
    if path in PUBLIC_ROUTES:
        return None
    return _RULE_INDEX.get((method, path))


def audit_coverage(routes: Iterable[tuple[str, str]]) -> CoverageReport:
    """Classify each ``(method, path)`` route into mapped / public / unmapped.

    Fail-closed («запрет по умолчанию»): any route that is neither mapped nor
    public lands in ``unmapped``. Output ordering is deterministic — sections
    preserve first-seen input order and de-duplicate repeats.
    """
    mapped: list[EndpointRule] = []
    public: list[tuple[str, str]] = []
    unmapped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for method, path in routes:
        key = (method, path)
        if key in seen:
            continue
        seen.add(key)
        if path in PUBLIC_ROUTES:
            public.append(key)
        elif key in _RULE_INDEX:
            mapped.append(EndpointRule(method, path, _RULE_INDEX[key]))
        else:
            unmapped.append(key)
    return CoverageReport(tuple(mapped), tuple(public), tuple(unmapped))
