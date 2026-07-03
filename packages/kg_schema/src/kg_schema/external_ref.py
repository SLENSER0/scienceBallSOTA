"""Graph-side ExternalRef node DTO + payload-hash idempotency (§20.3).

Внешняя ссылка (*external reference*) связывает узел графа с записью во внешней
системе — источнике данных (elabFTW, openBIS, Materials Project, MatKG, MatScholar,
Propnet). Каждая такая ссылка описывается неизменяемой записью :class:`ExternalRef`:
из какой системы (``system``) и с каким версионным тегом (``system_version``), какой
внешний идентификатор (``external_id``) и URL (``external_url``), когда была получена
(``fetched_at``) и с каким хешем полезной нагрузки (``payload_hash``).

Это графовая сторона (*graph side*) — DTO для узла ``:ExternalRef``; она отлична от
SQL-кросоувока (*crosswalk*) в :mod:`kg_common.storage.entity_mapping`, который держит
реляционное соответствие «локальная сущность ↔ внешний ключ». Здесь же —
идемпотентность на основе хеша полезной нагрузки (*payload-hash idempotency*): если
внешняя запись не изменилась, её ``payload_hash`` совпадёт, и повторный upsert можно
пропустить (§8.9).

``id`` детерминирован (*deterministic*): :func:`make_external_ref` выводит его из
SHA-1 ключа ``{system}:{external_id}``, поэтому одна и та же внешняя запись всегда
получает один и тот же идентификатор узла — воспроизводимо для тестов и upsert.

Kuzu note: кастомные свойства узла (``system``, ``payload_hash`` …) НЕ являются
запрашиваемыми колонками — их читают через ``get_node()``; в ``RETURN`` идут только
базовые колонки. Поэтому запись сериализуется плоским :meth:`ExternalRef.as_dict`,
пригодным для property-map узла ``:ExternalRef`` (§8.2).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# External source systems allowed as ExternalRef.system (§20.3). Anything outside this
# set is rejected by make_external_ref so the graph never references an unknown source.
ALLOWED_SYSTEMS: frozenset[str] = frozenset(
    {"elabftw", "openbis", "materials_project", "matkg", "matscholar", "propnet"}
)

# Length of the hex digests kept for the node id (SHA-1) and payload hash (SHA-256).
_ID_HEX_LEN = 16
_PAYLOAD_HEX_LEN = 16


@dataclass(frozen=True)
class ExternalRef:
    """Immutable DTO for one ``:ExternalRef`` graph node (§20.3).

    Attributes
    ----------
    id:
        Deterministic node id ``"extref:" + sha1({system}:{external_id})[:16]``.
    system:
        External source system; always a member of :data:`ALLOWED_SYSTEMS`.
    external_id:
        Identifier of the record inside ``system`` (e.g. ``"mp-149"``).
    external_url:
        Canonical URL of the external record, if known.
    system_version:
        Version tag of the external system / dataset at fetch time.
    fetched_at:
        ISO-8601 timestamp when the external record was fetched.
    payload_hash:
        SHA-256 over the canonical JSON of the fetched payload (``[:16]``); the
        basis for payload-hash idempotency (§8.9).
    """

    id: str
    system: str
    external_id: str
    external_url: str
    system_version: str
    fetched_at: str
    payload_hash: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§20.3).

        Carries exactly the seven fields, ready as a property-map for the
        ``:ExternalRef`` node. Round-trips via ``ExternalRef(**ref.as_dict())``.
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


def external_ref_key(system: str, external_id: str) -> str:
    """Return the natural key ``"{system}:{external_id}"`` for an external ref (§20.3)."""
    return f"{system}:{external_id}"


def _payload_hash(payload: Mapping[str, Any] | None) -> str:
    """Hash a payload deterministically via canonical JSON (§20.3).

    Uses ``json.dumps(payload, sort_keys=True)`` so key order does not affect the
    digest, then SHA-256 truncated to :data:`_PAYLOAD_HEX_LEN`. ``None`` hashes as
    an empty object ``{}``.
    """
    canonical = json.dumps(payload or {}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:_PAYLOAD_HEX_LEN]


def make_external_ref(
    system: str,
    external_id: str,
    *,
    external_url: str = "",
    system_version: str = "",
    fetched_at: str = "",
    payload: Mapping[str, Any] | None = None,
) -> ExternalRef:
    """Build an :class:`ExternalRef` with a deterministic id and payload hash (§20.3).

    The ``id`` is ``"extref:" + sha1(external_ref_key(...))[:16]`` and the
    ``payload_hash`` is the canonical hash of ``payload`` (see :func:`_payload_hash`),
    so the same external record always yields the same node — idempotent upsert (§8.9).

    Raises
    ------
    ValueError
        If ``system`` is not a member of :data:`ALLOWED_SYSTEMS`.
    """
    if system not in ALLOWED_SYSTEMS:
        allowed = ", ".join(sorted(ALLOWED_SYSTEMS))
        raise ValueError(f"unknown external system {system!r}; allowed: {allowed}")
    key = external_ref_key(system, external_id)
    node_id = "extref:" + hashlib.sha1(key.encode()).hexdigest()[:_ID_HEX_LEN]
    return ExternalRef(
        id=node_id,
        system=system,
        external_id=external_id,
        external_url=external_url,
        system_version=system_version,
        fetched_at=fetched_at,
        payload_hash=_payload_hash(payload),
    )


def is_changed(prev: ExternalRef, new_payload: Mapping[str, Any]) -> bool:
    """Return ``True`` iff ``new_payload`` hashes differently from ``prev`` (§20.3).

    The recomputed payload hash is compared to ``prev.payload_hash``; equality means
    the external record is unchanged and the upsert can be skipped (§8.9).
    """
    return _payload_hash(new_payload) != prev.payload_hash
