"""GraphRAG Qdrant collection alias planner — blue/green swap + retention.

§11.10 Blue/green Qdrant collection alias planning / Планирование alias Qdrant.

RU: Чистый планировщик blue/green-переключения alias коллекции Qdrant для
сводок сообществ GraphRAG и удержания (retention) последних K коллекций.
Отличается от graphrag_build_registry, который отслеживает *записи* сборок,
а не имена коллекций Qdrant. Alias всегда указывает на активную коллекцию,
а активная коллекция НИКОГДА не попадает в to_drop.
EN: Pure planner for the blue/green swap of a Qdrant collection alias holding
GraphRAG community summaries plus retention of the newest K collections.
Distinct from graphrag_build_registry, which tracks build *records* rather
than Qdrant collection names. The alias always points at the active
collection, and the active collection is NEVER placed into to_drop.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_BASE = "graphrag_community_summaries"


@dataclass(frozen=True)
class AliasPlan:
    """Immutable plan for one alias swap / Неизменяемый план переключения alias.

    RU: alias — имя alias-коллекции (базовое имя), active_collection — коллекция,
    на которую alias будет указывать; to_keep/to_drop — коллекции, которые
    сохраняются/удаляются в рамках retention.
    EN: alias is the alias name (the base name), active_collection is the
    collection the alias will point to; to_keep/to_drop are the collections
    retained/pruned by the retention step.
    """

    alias: str
    active_collection: str
    to_keep: tuple[str, ...]
    to_drop: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a plain dict view / Вернуть словарное представление."""
        return {
            "alias": self.alias,
            "active_collection": self.active_collection,
            "to_keep": list(self.to_keep),
            "to_drop": list(self.to_drop),
        }


def collection_name(build_version: str, base: str = _DEFAULT_BASE) -> str:
    """Return the Qdrant collection name for a build / Имя коллекции для сборки.

    RU: Детерминированное имя коллекции вида f'{base}_{build_version}'.
    EN: Deterministic collection name shaped as f'{base}_{build_version}'.
    """
    return f"{base}_{build_version}"


def plan_swap(
    active_version: str,
    all_versions: Sequence[str],
    retain_k: int,
    base: str = _DEFAULT_BASE,
) -> AliasPlan:
    """Plan a blue/green alias swap with retention / Спланировать swap с retention.

    RU: alias указывает на collection_name(active). Сохраняются активная
    коллекция и новейшие retain_k коллекций (all_versions трактуются
    oldest->newest); остальное — в to_drop. Активная коллекция никогда не
    удаляется. sum(len(to_keep)+len(to_drop)) == len(all_versions).
    EN: The alias points at collection_name(active). Keep the active collection
    plus the newest retain_k collections (all_versions treated oldest->newest);
    everything else goes to to_drop. The active collection is never dropped.
    sum(len(to_keep)+len(to_drop)) == len(all_versions).
    """
    if retain_k < 0:
        raise ValueError(f"retain_k must be >= 0, got {retain_k}")
    active_collection = collection_name(active_version, base)
    # RU: новейшие retain_k среди неактивных версий (хвост списка).
    # EN: newest retain_k among the non-active versions (tail of the list).
    non_active = [v for v in all_versions if v != active_version]
    newest = non_active[len(non_active) - retain_k :] if retain_k else []
    keep_versions = set(newest)
    keep_versions.add(active_version)
    to_keep: list[str] = []
    to_drop: list[str] = []
    for version in all_versions:
        name = collection_name(version, base)
        if version in keep_versions:
            to_keep.append(name)
        else:
            to_drop.append(name)
    return AliasPlan(
        alias=base,
        active_collection=active_collection,
        to_keep=tuple(to_keep),
        to_drop=tuple(to_drop),
    )
