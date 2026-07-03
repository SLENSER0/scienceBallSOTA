"""Planner for the §16.6 human ``alias_add`` action (RU/EN).

Чистый планировщик (pure planner) для добавления синонимов (aliases) к
сущности: нормализует кандидатов, отбрасывает дубликаты и уже известные
поверхности, помечает коллизии с каноническими именами **других** сущностей —
но **не пишет** в граф. This lets ``alias_add`` be previewed and validated
before any Kuzu write; the resulting surfaces feed ``aliases_text`` fulltext.

``canonical_names`` maps a *normalized* canonical name to the entity id that
owns it. A candidate that normalizes to another entity's canonical name is a
collision; the same normalized name owned by *this* entity is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def _norm(s: str) -> str:
    """Normalize an alias surface: strip, casefold, collapse whitespace.

    Нормализация: обрезка краёв, приведение регистра (casefold) и схлопывание
    любых пробельных последовательностей в один пробел.
    """
    return " ".join(s.strip().casefold().split())


@dataclass(frozen=True)
class AliasAddPlan:
    """Planned outcome of one ``alias_add`` action (§16.6).

    План добавления синонимов. ``added`` — новые нормализованные поверхности,
    реально добавляемые; ``aliases`` — итоговый отсортированный список синонимов
    сущности (нормализованный, без самого имени). ``noop`` — нечего добавлять;
    ``collision`` — кандидат совпал с каноническим именем другой сущности, и
    ``collision_owner`` держит её id.
    """

    entity_id: str
    added: list[str]
    aliases: list[str]
    noop: bool
    collision: bool
    collision_owner: str | None

    def as_dict(self) -> dict:
        """Return a JSON-friendly plain-``dict`` view (сериализуемый вид)."""
        return {
            "entity_id": self.entity_id,
            "added": list(self.added),
            "aliases": list(self.aliases),
            "noop": self.noop,
            "collision": self.collision,
            "collision_owner": self.collision_owner,
        }


def plan_alias_add(
    entity: Mapping,
    new_aliases: Sequence[str],
    canonical_names: Mapping[str, str],
) -> AliasAddPlan:
    """Compute an :class:`AliasAddPlan` for adding ``new_aliases`` (§16.6).

    ``entity`` needs ``id``, ``name`` and (optionally) ``aliases``. Each
    candidate is normalized via :func:`_norm`; candidates already equal (case-
    insensitively) to the entity name or an existing alias are skipped, and
    whitespace/case variants of one candidate de-duplicate to a single add.

    A normalized candidate that is the canonical name of a **different** entity
    in ``canonical_names`` sets ``collision`` / ``collision_owner`` and is not
    added; the entity's own canonical name does not collide.
    """
    entity_id = str(entity["id"])
    existing = list(entity.get("aliases") or [])

    existing_norms = {n for n in (_norm(a) for a in existing) if n}
    name_norm = _norm(str(entity.get("name", "")))
    skip_norms = existing_norms | ({name_norm} if name_norm else set())

    added: list[str] = []
    seen_added: set[str] = set()
    collision = False
    collision_owner: str | None = None

    for candidate in new_aliases:
        norm = _norm(candidate)
        if not norm:
            continue
        owner = canonical_names.get(norm)
        if owner is not None and owner != entity_id:
            collision = True
            if collision_owner is None:
                collision_owner = owner
            continue
        if norm in skip_norms or norm in seen_added:
            continue
        seen_added.add(norm)
        added.append(norm)

    aliases = sorted(existing_norms | set(added))
    return AliasAddPlan(
        entity_id=entity_id,
        added=added,
        aliases=aliases,
        noop=not added,
        collision=collision,
        collision_owner=collision_owner,
    )
