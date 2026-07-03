"""Parameterized read-only Cypher template library (§12.10).

Text2Cypher-free query surface: the agent never emits free-form Cypher, it
picks a *named* template from :data:`TEMPLATES` and supplies bound parameters.
Каждый шаблон (template) — строго read-only, параметризован через ``$name``
placeholders, ограничен ``LIMIT`` и заранее прогнан через
:func:`graph_service.cypher_guard.guard_read_query`. This gives two layers of
safety: templates are hand-audited and immutable, and every rendered query is
re-validated by the guard (mutating clause / write procedure → refused).

Kuzu note: custom node properties are **not** queryable columns — the graph is
a single ``:Node`` table (``label`` discriminator) with a ``:Rel`` edge table
(``type`` discriminator), so templates ``RETURN`` base columns / ids only; the
caller reads the remaining fields back via ``KuzuGraphStore.get_node(id)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from graph_service.cypher_guard import guard_read_query

# ``$name`` placeholder — bound parameter, never string-concatenated (§19.6).
_PLACEHOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _placeholders(cypher: str) -> tuple[str, ...]:
    """Ordered, de-duplicated ``$name`` placeholders in ``cypher`` (плейсхолдеры)."""
    seen: dict[str, None] = {}
    for match in _PLACEHOLDER.finditer(cypher):
        seen.setdefault(match.group(1), None)
    return tuple(seen)


@dataclass(frozen=True, slots=True)
class CypherTemplate:
    """One named, read-only, parameterized Cypher template (§12.10).

    ``params`` are the ``$name`` placeholders the caller must bind; they are the
    query's *only* variable inputs (bound separately, never interpolated).
    """

    name: str
    cypher: str
    params: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialize to the client-facing ``{name, cypher, params}`` shape."""
        return {"name": self.name, "cypher": self.cypher, "params": list(self.params)}


def _make(name: str, cypher: str) -> CypherTemplate:
    """Build a template, failing fast (fail-fast) if it is not guard-clean.

    Running :func:`guard_read_query` at construction guarantees every registry
    entry is read-only + ``LIMIT``-bounded before the module finishes importing.
    """
    guard_read_query(cypher)  # raises CypherGuardError if a template regresses
    body = cypher.strip()
    return CypherTemplate(name=name, cypher=body, params=_placeholders(body))


# -- template registry (реестр шаблонов) -----------------------------------
# Every query: single ``:Node`` / ``:Rel`` model, ``$name`` params, literal
# ``LIMIT``, base-column RETURNs only (custom props via ``get_node``).

_material_regime_property = _make(
    "material_regime_property",
    "MATCH (mat:Node {id: $material_id})-[:Rel]-(meas:Node)\n"
    "WHERE meas.label = 'Measurement'\n"
    "MATCH (meas)-[:Rel {type: 'OF_PROPERTY'}]->(prop:Node {id: $property_id})\n"
    "MATCH (meas)-[:Rel {type: 'ABOUT_REGIME'}]->(reg:Node {id: $regime_id})\n"
    "RETURN meas.id, meas.label, mat.id, prop.id, reg.id\n"
    "LIMIT 200",
)

_entity_neighbors = _make(
    "entity_neighbors",
    "MATCH (n:Node {id: $entity_id})-[r:Rel]-(nbr:Node)\n"
    "RETURN n.id, r.type, nbr.id, nbr.label\n"
    "LIMIT 100",
)

_shortest_path = _make(
    "shortest_path",
    "MATCH (src:Node {id: $source_id}), (dst:Node {id: $target_id})\n"
    "MATCH path = (src)-[:Rel* SHORTEST 1..6]-(dst)\n"
    "RETURN src.id, dst.id, length(path) AS hops\n"
    "LIMIT 10",
)

_measurements_for_material = _make(
    "measurements_for_material",
    "MATCH (mat:Node {id: $material_id})-[:Rel]-(meas:Node)\n"
    "WHERE meas.label = 'Measurement'\n"
    "OPTIONAL MATCH (meas)-[:Rel {type: 'OF_PROPERTY'}]->(prop:Node)\n"
    "OPTIONAL MATCH (meas)-[:Rel {type: 'HAS_UNIT'}]->(unit:Node)\n"
    "RETURN meas.id, meas.label, prop.id, unit.id\n"
    "LIMIT 200",
)

TEMPLATES: dict[str, CypherTemplate] = {
    template.name: template
    for template in (
        _material_regime_property,
        _entity_neighbors,
        _shortest_path,
        _measurements_for_material,
    )
}


def list_templates() -> tuple[str, ...]:
    """Return the registered template names (имена шаблонов), in registry order."""
    return tuple(TEMPLATES)


def get_template(name: str) -> CypherTemplate:
    """Look up a template by name; raise ``KeyError`` if it is unknown."""
    try:
        return TEMPLATES[name]
    except KeyError:
        raise KeyError(f"unknown template: {name!r}") from None


def render(name: str, **params: object) -> tuple[str, dict[str, object]]:
    """Render a template to ``(cypher, params)`` for ``KuzuGraphStore.rows``.

    Validates that exactly the template's required ``$name`` placeholders are
    bound (missing → ``ValueError``, unexpected → ``ValueError``, unknown
    template → ``KeyError``), then re-runs the guard so the returned Cypher is
    provably read-only + ``LIMIT``-bounded. Params are returned as a dict to be
    passed *separately* (never interpolated) — Cypher-injection defense.
    """
    template = get_template(name)
    required = set(template.params)
    given = set(params)
    missing = required - given
    if missing:
        raise ValueError(f"template {name!r} missing params: {sorted(missing)}")
    unexpected = given - required
    if unexpected:
        raise ValueError(f"template {name!r} got unexpected params: {sorted(unexpected)}")
    cypher = guard_read_query(template.cypher)
    return cypher, dict(params)
