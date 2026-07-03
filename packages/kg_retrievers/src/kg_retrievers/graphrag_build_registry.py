"""GraphRAG build registry — blue/green versioning of community builds.

§11.10 GraphRAG build registry / Реестр сборок GraphRAG.

RU: Реестр сборок GraphRAG-графа сообществ. Поддерживает blue/green
переключение активной версии, откат (rollback) и удержание (retain)
последних K сборок, никогда не удаляя активную.
EN: Registry of GraphRAG community builds. Supports blue/green swap of the
active version, rollback to the previously-active build, and retain of the
newest K builds while never pruning the active one.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

_VALID_STATUS = frozenset({"built", "failed", "indexing"})


@dataclass(frozen=True)
class BuildRecord:
    """Immutable record of a single GraphRAG build / Запись одной сборки.

    RU: Неизменяемая запись о сборке графа сообществ.
    EN: Frozen record describing one community build and its active flag.
    """

    build_version: str
    status: str
    n_communities: int
    created_at: str
    active: bool

    def as_dict(self) -> dict[str, object]:
        """Return a plain dict view / Вернуть словарное представление."""
        return {
            "build_version": self.build_version,
            "status": self.status,
            "n_communities": self.n_communities,
            "created_at": self.created_at,
            "active": bool(self.active),
        }


class BuildRegistry:
    """Mutable ordered registry of builds / Изменяемый реестр сборок.

    RU: Хранит упорядоченный словарь записей сборок и управляет активной
    версией по схеме blue/green.
    EN: Holds an ordered dict of build records and manages the active version
    using a blue/green swap.
    """

    def __init__(self) -> None:
        self._records: OrderedDict[str, BuildRecord] = OrderedDict()
        # RU: стек ранее активных built-версий для rollback().
        # EN: stack of previously-active built versions used by rollback().
        self._active_history: list[str] = []

    def register(
        self,
        build_version: str,
        n_communities: int,
        created_at: str,
        status: str = "built",
    ) -> BuildRecord:
        """Register a new build / Зарегистрировать новую сборку.

        RU: status должен быть одним из {'built','failed','indexing'};
        повторная регистрация той же версии запрещена.
        EN: status must be one of {'built','failed','indexing'}; duplicate
        build_version raises ValueError.
        """
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status!r}")
        if build_version in self._records:
            raise ValueError(f"duplicate build_version: {build_version!r}")
        record = BuildRecord(
            build_version=build_version,
            status=status,
            n_communities=n_communities,
            created_at=created_at,
            active=False,
        )
        self._records[build_version] = record
        return record

    def activate(self, build_version: str) -> None:
        """Blue/green-swap the active flag to one version / Активировать версию.

        RU: Активной становится ровно одна версия и только если её
        status=='built'. Для 'failed'/'indexing'/отсутствующей — ValueError.
        EN: Exactly one version becomes active, only if its status=='built'.
        Raises ValueError for failed/indexing/missing builds.
        """
        if build_version not in self._records:
            raise ValueError(f"unknown build_version: {build_version!r}")
        target = self._records[build_version]
        if target.status != "built":
            raise ValueError(
                f"cannot activate build with status {target.status!r}: {build_version!r}"
            )
        current = self.active_version()
        if current == build_version:
            return
        if current is not None:
            self._active_history.append(current)
        for version, record in self._records.items():
            want_active = version == build_version
            if record.active != want_active:
                self._records[version] = _with_active(record, want_active)

    def active_version(self) -> str | None:
        """Return the active build_version or None / Активная версия или None."""
        for version, record in self._records.items():
            if record.active:
                return version
        return None

    def rollback(self) -> str:
        """Re-activate the previously-active built version / Откат к прошлой.

        RU: Возвращает build_version, ставший активным; ищет самую свежую
        ранее активную built-версию. ValueError, если истории нет.
        EN: Returns the build_version that becomes active again by re-activating
        the most recent previously-active built version. Raises ValueError if
        there is no eligible history.
        """
        while self._active_history:
            candidate = self._active_history.pop()
            record = self._records.get(candidate)
            if record is not None and record.status == "built":
                self.activate(candidate)
                # RU: activate записал текущую версию в историю — убираем её,
                # чтобы rollback был чистым переключением, а не накоплением.
                # EN: activate pushed the current version onto history; drop it
                # so rollback stays a clean swap rather than re-stacking.
                if self._active_history and self._active_history[-1] != candidate:
                    self._active_history.pop()
                return candidate
        raise ValueError("no previously-active built version to rollback to")

    def retain(self, keep: int) -> list[str]:
        """Prune all but the newest K builds / Оставить последние K сборок.

        RU: Возвращает список удалённых build_version, сохраняя самые новые K
        по порядку регистрации и никогда не удаляя активную.
        EN: Returns pruned build_versions, keeping the newest K by registration
        order and never removing the active build.
        """
        if keep < 0:
            raise ValueError(f"keep must be >= 0, got {keep}")
        versions = list(self._records.keys())
        active = self.active_version()
        # RU: новейшие K — хвост упорядоченного словаря.
        # EN: newest K are the tail of the ordered dict.
        keep_set = set(versions[len(versions) - keep :]) if keep else set()
        if active is not None:
            keep_set.add(active)
        pruned: list[str] = []
        for version in versions:
            if version not in keep_set:
                del self._records[version]
                pruned.append(version)
        self._active_history = [v for v in self._active_history if v in self._records]
        return pruned

    def records(self) -> list[BuildRecord]:
        """Return records in registration order / Записи в порядке регистрации."""
        return list(self._records.values())


def _with_active(record: BuildRecord, active: bool) -> BuildRecord:
    """Return a copy with a new active flag / Копия с новым флагом active."""
    return BuildRecord(
        build_version=record.build_version,
        status=record.status,
        n_communities=record.n_communities,
        created_at=record.created_at,
        active=active,
    )
