"""Report data-reference resolvability check — dangling ``[Data: …]`` refs (§11.11).

Cross-checks the inline ``[Data: …]`` references parsed from a community-report
body against the *known id universe* (entities / relationships / reports),
surfacing **dangling** references — ids a summary invents that resolve to no
known record. Complements :mod:`community_report_data_refs`, which only parses
the markers: no existing module validates report-internal refs. Pure and
read-only — the caller supplies the id universe.

Проверяет разрешимость встроенных ссылок ``[Data: …]`` из текста отчёта
сообщества относительно известного множества идентификаторов (сущности /
связи / отчёты) и выявляет «висячие» ссылки — выдуманные пересказом id,
которым не соответствует ни одна запись.

Rules:
- markers are parsed via :func:`community_report_data_refs.parse_data_refs`;
- each id is bucketed as *resolved* or *dangling* by its canonical record type
  (``Entities`` -> ``known_entity_ids``, ``Relationships`` ->
  ``known_relationship_ids``, ``Reports`` -> ``known_report_ids``);
- any *unknown* record type has all of its ids counted as dangling under that
  type key (there is no id universe to resolve them against);
- ``resolved_fraction`` is ``resolved_refs / total_refs``, and is a vacuous
  ``1.0`` when there are no references at all.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from kg_retrievers.community_report_data_refs import parse_data_refs

# Canonical record type -> keyword of the known-id set that resolves it.
_KNOWN_KEY_BY_TYPE = {
    "Entities": "known_entity_ids",
    "Relationships": "known_relationship_ids",
    "Reports": "known_report_ids",
}


@dataclass(frozen=True)
class RefCheckResult:
    """Resolvability of inline report references against a known id universe.

    - ``total_refs`` — total ``(type, id)`` references across all record types;
    - ``resolved_refs`` — how many of those resolve to a known id;
    - ``dangling`` — canonical type -> sorted tuple of unresolved ids (only
      types that actually have dangling ids appear);
    - ``resolved_fraction`` — ``resolved_refs / total_refs`` (``1.0`` when
      there are no references at all).
    """

    total_refs: int
    resolved_refs: int
    dangling: dict[str, tuple[int, ...]]
    resolved_fraction: float

    def as_dict(self) -> dict[str, object]:
        """Serialize to a plain JSON-friendly dict (tuples -> lists)."""
        return {
            "total_refs": self.total_refs,
            "resolved_refs": self.resolved_refs,
            "dangling": {k: list(v) for k, v in self.dangling.items()},
            "resolved_fraction": self.resolved_fraction,
        }


def check_references(
    text: str,
    *,
    known_entity_ids: Iterable[int] = (),
    known_relationship_ids: Iterable[int] = (),
    known_report_ids: Iterable[int] = (),
) -> RefCheckResult:
    """Check inline ``[Data: …]`` refs in ``text`` against the known id universe.

    Parses markers via :func:`parse_data_refs`, then buckets each id as resolved
    or dangling by its canonical record type. Ids of *unknown* record types are
    all treated as dangling under that type key.
    """
    known: dict[str, set[int]] = {
        "known_entity_ids": set(known_entity_ids),
        "known_relationship_ids": set(known_relationship_ids),
        "known_report_ids": set(known_report_ids),
    }

    refs = parse_data_refs(text)
    total_refs = 0
    resolved_refs = 0
    dangling: dict[str, tuple[int, ...]] = {}

    for rec_type, ids in refs.by_type.items():
        total_refs += len(ids)
        known_key = _KNOWN_KEY_BY_TYPE.get(rec_type)
        universe = known[known_key] if known_key is not None else set()
        missing = tuple(rid for rid in ids if rid not in universe)
        resolved_refs += len(ids) - len(missing)
        if missing:
            dangling[rec_type] = missing

    resolved_fraction = 1.0 if total_refs == 0 else resolved_refs / total_refs
    return RefCheckResult(
        total_refs=total_refs,
        resolved_refs=resolved_refs,
        dangling=dangling,
        resolved_fraction=resolved_fraction,
    )
