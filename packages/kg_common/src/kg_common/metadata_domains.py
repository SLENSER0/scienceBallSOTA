"""Catalog domains grouped by Lab — каталожные домены по лабораториям (§10.6).

Per §10.6 the metadata catalog exposes one *Domain* per *Lab*: «each Lab → domain;
bind sources of that lab to the domain». A Domain is a small, immutable grouping
that names the lab and lists the ``source_id``s belonging to it, so downstream
navigation ("browse the catalog by lab") is deterministic and side-effect free.

Everything here is pure: no I/O, no wall-clock, no mutated globals. A
:class:`Domain` is a frozen dataclass, so callers cannot mutate it after
construction — grouping/assignment helpers always return *new* lists.

Public API:

* :class:`Domain`       — frozen ``{domain_id, lab_id, name, source_ids}`` record.
* :func:`domain_id_for` — deterministic ``"domain:" + slug(lab_id)`` id.
* :func:`build_domains` — group source rows into domains, sorted deterministically.
* :func:`orphan_sources` — ``source_id``s that carry no ``lab_id`` (excluded above).
* :func:`assign`        — idempotently add a source to the matching domain.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from kg_common.ids import slugify

__all__ = [
    "Domain",
    "domain_id_for",
    "build_domains",
    "orphan_sources",
    "assign",
]


# --------------------------------------------------------------------------- #
# Domain record — запись домена                                               #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Domain:
    """A catalog domain for one lab — каталожный домен одной лаборатории."""

    domain_id: str
    lab_id: str
    name: str
    source_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping (``source_ids`` as list) — отображение."""
        return {
            "domain_id": self.domain_id,
            "lab_id": self.lab_id,
            "name": self.name,
            "source_ids": list(self.source_ids),
        }


# --------------------------------------------------------------------------- #
# Identity — идентификатор домена                                             #
# --------------------------------------------------------------------------- #


def domain_id_for(lab_id: str) -> str:
    """Deterministic domain id ``"domain:" + slug(lab_id)`` — id домена по лабе."""
    return f"domain:{slugify(lab_id)}"


# --------------------------------------------------------------------------- #
# Grouping — группировка источников                                           #
# --------------------------------------------------------------------------- #


def build_domains(sources: Iterable[Mapping[str, object]]) -> list[Domain]:
    """Group source rows into domains by lab — сгруппировать источники в домены.

    Each row is a mapping with keys ``source_id``, ``lab_id`` and ``lab_name``.
    Rows missing a truthy ``lab_id`` are excluded (see :func:`orphan_sources`).
    The result is sorted by ``domain_id`` and each ``source_ids`` tuple is sorted;
    duplicate ``source_id``s within a lab are collapsed.
    """
    grouped: dict[str, dict[str, object]] = {}
    for row in sources:
        lab_id = row.get("lab_id")
        source_id = row.get("source_id")
        if not lab_id or not source_id:
            continue
        lab_id = str(lab_id)
        did = domain_id_for(lab_id)
        bucket = grouped.get(did)
        if bucket is None:
            bucket = {
                "lab_id": lab_id,
                "name": str(row.get("lab_name") or lab_id),
                "source_ids": set(),
            }
            grouped[did] = bucket
        sid_set: set[str] = bucket["source_ids"]  # type: ignore[assignment]
        sid_set.add(str(source_id))

    return [
        Domain(
            domain_id=did,
            lab_id=str(bucket["lab_id"]),
            name=str(bucket["name"]),
            source_ids=tuple(sorted(bucket["source_ids"])),  # type: ignore[arg-type]
        )
        for did, bucket in sorted(grouped.items())
    ]


def orphan_sources(sources: Iterable[Mapping[str, object]]) -> list[str]:
    """Return ``source_id``s with no ``lab_id`` — источники без лаборатории.

    These rows are excluded from :func:`build_domains`; the order follows input.
    """
    out: list[str] = []
    for row in sources:
        source_id = row.get("source_id")
        if source_id and not row.get("lab_id"):
            out.append(str(source_id))
    return out


# --------------------------------------------------------------------------- #
# Assignment — идемпотентная привязка источника                               #
# --------------------------------------------------------------------------- #


def assign(
    domains: Iterable[Domain],
    source_id: str,
    lab_id: str,
    lab_name: str,
) -> list[Domain]:
    """Idempotently bind ``source_id`` to its lab's domain — привязать источник.

    Returns a new list. The domain for ``lab_id`` is created if absent; if the
    source is already present it is left untouched (no duplicates). The result is
    sorted by ``domain_id`` and each ``source_ids`` tuple stays sorted.
    """
    did = domain_id_for(lab_id)
    by_id = {d.domain_id: d for d in domains}
    existing = by_id.get(did)
    if existing is None:
        by_id[did] = Domain(
            domain_id=did,
            lab_id=lab_id,
            name=lab_name or lab_id,
            source_ids=(source_id,),
        )
    elif source_id not in existing.source_ids:
        by_id[did] = Domain(
            domain_id=existing.domain_id,
            lab_id=existing.lab_id,
            name=existing.name,
            source_ids=tuple(sorted((*existing.source_ids, source_id))),
        )
    return [by_id[k] for k in sorted(by_id)]
