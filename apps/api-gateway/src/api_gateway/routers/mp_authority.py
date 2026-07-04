"""Materials Project authority badge for an entity (§8.2 / §20.3 / §20.6).

Surfaces the *external-authority* link that the pipeline already writes when a
canonical Material/Alloy is crosswalked to a Materials Project record: the MP
material id (``mp-XXXX``) and the canonical chemical formula. A single read-only
endpoint powers a small "✓ Materials Project mp-XXXX" trust badge on the Entity
Detail screen (§17.11) — instant, hand-checkable evidence that the alloy was
canonicalised against an external authority rather than only mention-clustered.

Where the link lives (checked in order, all handled gracefully):

1. **Node attributes** — the resolved entity node may carry the MP id inline as
   one of :data:`MP_ID_KEYS` (e.g. ``mp_id`` / ``mp_material_id``), or as a
   generic ``(external_system, external_id)`` pair pointing at
   ``materials_project``. The canonical formula comes from :data:`FORMULA_KEYS`.
2. **ExternalRef node** — an ``ExternalRef`` provenance node (§20.3,
   ``system='materials_project'``) linked to the entity via ``HAS_EXTERNAL_REF``;
   it carries ``external_id`` and an optional ``external_url``.

No network I/O to the live MP API — this reads only what is already persisted in
the graph, so the badge is reproducible and offline-safe. Pure lookups + a
deterministic URL builder; the store call is a parameterised read (no raw Cypher
from the client, §14.6).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/entities", tags=["entities"])

#: External-system code for Materials Project (matches ``kg_schema`` VALID_SYSTEMS).
MP_SYSTEM = "materials_project"

#: Public MP material page; ``{mp_id}`` is appended to build the canonical link.
MP_BASE_URL = "https://materialsproject.org/materials/"

#: Node-attribute keys that may hold the MP material id inline (priority order).
MP_ID_KEYS: tuple[str, ...] = ("mp_id", "mp_material_id", "materials_project_id")

#: Node-attribute keys naming the external system for a generic crosswalk pair.
SYSTEM_KEYS: tuple[str, ...] = ("external_system", "source_system", "authority")

#: Node-attribute keys that may hold the canonical formula (priority order).
FORMULA_KEYS: tuple[str, ...] = (
    "canonical_formula",
    "formula",
    "normalized_formula",
    "reduced_formula",
    "pretty_formula",
)

#: Node-attribute keys that may hold an explicit MP record URL.
URL_KEYS: tuple[str, ...] = ("mp_url", "external_url")

# An MP id is a lowercase code such as ``mp-6930`` / ``mvc-1234`` (letters + '-' +
# digits), or a bare numeric id we canonicalise by prefixing ``mp-``.
_BARE_NUMERIC = re.compile(r"^\d+$")


def _first(props: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty string value among ``keys`` (или None)."""
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def normalize_mp_id(raw: str | None) -> str | None:
    """Canonicalise a raw MP id to ``mp-XXXX`` form (нормализация mp_id).

    ``'  MP-6930 '`` → ``'mp-6930'``; a bare ``'6930'`` → ``'mp-6930'``; an id that
    already carries a system prefix (``'mvc-1234'``) is kept, lowercased. Empty or
    ``None`` input yields ``None``.
    """
    if raw is None:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    if _BARE_NUMERIC.match(text):
        return f"mp-{text}"
    return text


def _mp_id_from_props(props: dict[str, Any]) -> str | None:
    """Extract an MP id from node attributes (inline key or crosswalk pair)."""
    inline = _first(props, MP_ID_KEYS)
    if inline:
        return normalize_mp_id(inline)
    system = _first(props, SYSTEM_KEYS)
    if system and system.strip().lower() == MP_SYSTEM:
        return normalize_mp_id(_first(props, ("external_id",)))
    return None


def mp_url(mp_id: str, explicit: str | None = None) -> str:
    """Build the MP record URL — explicit link wins, else derive from ``mp_id``."""
    if explicit and explicit.strip():
        return explicit.strip()
    return f"{MP_BASE_URL}{mp_id}"


class MaterialsProjectBadge(BaseModel):
    """Materials Project authority badge payload for one entity (§8.2)."""

    entity_id: str
    has_authority: bool
    source_system: str = MP_SYSTEM
    mp_id: str | None = None
    canonical_formula: str | None = None
    url: str | None = None


def _scan_external_ref(store: Any, entity_id: str) -> tuple[str | None, str | None]:
    """Look for a linked ``ExternalRef(system=materials_project)`` neighbour (§20.3).

    Returns ``(mp_id, explicit_url)`` — either may be ``None``. Any store/lookup
    error degrades to ``(None, None)`` so the badge simply hides.
    """
    try:
        graph = store.neighbors(entity_id, depth=1)
    except Exception:  # a missing/edge-case store must not 500 the badge
        return None, None
    for node in graph.nodes:
        props = node.properties or {}
        system = str(props.get("system") or "").strip().lower()
        if system != MP_SYSTEM and str(node.type) != "ExternalRef":
            continue
        if system and system != MP_SYSTEM:
            continue
        ext_id = props.get("external_id")
        if ext_id:
            return normalize_mp_id(str(ext_id)), (props.get("external_url") or None)
    return None, None


@router.get("/{entity_id}/materials-project", response_model=MaterialsProjectBadge)
def materials_project_badge(entity_id: str) -> MaterialsProjectBadge:
    """Return the Materials Project authority link for ``entity_id`` (§8.2).

    Reads the persisted crosswalk (node attributes first, then a linked
    ``ExternalRef`` provenance node). ``has_authority`` is ``False`` — with the
    other fields ``None`` — when the entity is unknown or was never crosswalked to
    MP, so the frontend badge stays hidden without special-casing errors.
    """
    store = get_store()
    node = store.get_node(entity_id)
    if node is None:
        return MaterialsProjectBadge(entity_id=entity_id, has_authority=False)

    props = {k: v for k, v in node.items() if v is not None}
    formula = _first(props, FORMULA_KEYS)
    mp_id = _mp_id_from_props(props)
    explicit_url = _first(props, URL_KEYS)

    if not mp_id:
        mp_id, ref_url = _scan_external_ref(store, entity_id)
        explicit_url = explicit_url or ref_url

    if not mp_id:
        return MaterialsProjectBadge(
            entity_id=entity_id, has_authority=False, canonical_formula=formula
        )

    return MaterialsProjectBadge(
        entity_id=entity_id,
        has_authority=True,
        mp_id=mp_id,
        canonical_formula=formula,
        url=mp_url(mp_id, explicit_url),
    )
