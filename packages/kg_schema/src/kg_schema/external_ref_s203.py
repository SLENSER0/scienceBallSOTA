"""§20.3 — graph node model for external-system references (*external references*).

Модель узла ``ExternalRef`` (*external reference node*): детерминированная ссылка на
запись во внешней системе (§20.3) — eLabFTW, openBIS, Materials Project, MatKG,
MatScholar, propnet. Каждый узел фиксирует, *откуда* пришли данные и *какими они были*
в момент выборки, чтобы связанные сущности графа можно было провенанс-проверить и
переигрывать без обращения к живому API:

* **system** — код внешней системы из :data:`VALID_SYSTEMS` (контролируемый словарь).
* **external_id** — идентификатор записи в этой системе (напр. ``exp:12``).
* **external_url** — прямая ссылка на запись (опционально).
* **system_version** — версия/снимок внешней системы на момент выборки (опционально).
* **fetched_at** — ISO-метка времени выборки (опционально).
* **payload_hash** — sha256 канонического JSON исходной полезной нагрузки (*payload*),
  что даёт стабильный отпечаток контента для дедупликации и обнаружения дрейфа.

Сущность графа ссылается на узел ребром ``HAS_EXTERNAL_REF`` (см.
:func:`has_external_ref_edge`).

Kuzu note: кастомные свойства узла НЕ являются запрашиваемыми колонками — их читают через
``get_node()``, в ``RETURN`` идут только базовые колонки. ``ExternalRef`` описывает форму
узла и его сериализацию, данные графа он не хранит, поэтому ограничения не касается.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Controlled vocabulary of external systems this node may reference (§20.3). Codes are
# stable lowercase identifiers; keep them fixed across releases so ``ExternalRef.id`` and
# provenance edges remain valid over time.
VALID_SYSTEMS: frozenset[str] = frozenset(
    {
        "elabftw",
        "openbis",
        "materials_project",
        "matkg",
        "matscholar",
        "propnet",
    }
)


@dataclass(frozen=True)
class ExternalRef:
    """Immutable external-system reference node (§20.3).

    Attributes
    ----------
    id:
        Stable node id ``extref:{system}:{external_id}`` (§20.3); unique per external
        record so re-fetches map to the same node.
    system:
        External-system code from :data:`VALID_SYSTEMS`.
    external_id:
        Record identifier within ``system`` (e.g. ``exp:12``).
    external_url:
        Direct link to the record; empty string when unknown.
    system_version:
        Version/snapshot of the external system at fetch time; empty when unknown.
    fetched_at:
        ISO-8601 timestamp of the fetch; empty when unknown.
    payload_hash:
        sha256 hex of the canonical JSON payload (:func:`compute_payload_hash`).
    """

    id: str
    system: str
    external_id: str
    external_url: str
    system_version: str
    fetched_at: str
    payload_hash: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the canonical seven-field dict (§20.3).

        Field order mirrors the dataclass declaration; every attribute is a plain
        string, so the result is JSON- and frontend-friendly. ``len(...) == 7``.
        """
        return {
            "id": self.id,
            "system": self.system,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "system_version": self.system_version,
            "fetched_at": self.fetched_at,
            "payload_hash": self.payload_hash,
        }


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Return the sha256 hex digest of the canonical JSON of ``payload`` (§20.3).

    Canonicalisation uses ``json.dumps(payload, sort_keys=True)`` so the digest is
    independent of key insertion order (``{"a": 1, "b": 2}`` and ``{"b": 2, "a": 1}``
    hash identically) but sensitive to values (``{"a": 1}`` and ``{"a": 2}`` differ).
    """
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_external_ref(
    system: str,
    external_id: str,
    payload: dict[str, Any],
    external_url: str = "",
    system_version: str = "",
    fetched_at: str = "",
) -> ExternalRef:
    """Build an :class:`ExternalRef` for a record in an external system (§20.3).

    ``id`` is derived as ``extref:{system}:{external_id}`` and ``payload_hash`` as
    :func:`compute_payload_hash` of ``payload``. Raises :class:`ValueError` when
    ``system`` is not in :data:`VALID_SYSTEMS`.
    """
    if system not in VALID_SYSTEMS:
        raise ValueError(
            f"unknown external system {system!r}; expected one of {sorted(VALID_SYSTEMS)}"
        )
    return ExternalRef(
        id=f"extref:{system}:{external_id}",
        system=system,
        external_id=external_id,
        external_url=external_url,
        system_version=system_version,
        fetched_at=fetched_at,
        payload_hash=compute_payload_hash(payload),
    )


def has_external_ref_edge(entity_id: str, ref_id: str) -> dict[str, str]:
    """Build the ``HAS_EXTERNAL_REF`` edge from an entity to a ref node (§20.3).

    Returns ``{"type": "HAS_EXTERNAL_REF", "from": entity_id, "to": ref_id}`` — the
    provenance link a graph entity uses to point at its :class:`ExternalRef`.
    """
    return {"type": "HAS_EXTERNAL_REF", "from": entity_id, "to": ref_id}


__all__ = [
    "VALID_SYSTEMS",
    "ExternalRef",
    "compute_payload_hash",
    "has_external_ref_edge",
    "make_external_ref",
]
