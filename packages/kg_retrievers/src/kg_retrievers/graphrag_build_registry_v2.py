"""GraphRAG community-build registry with activation/rollback/prune (§11.10).

RU: Реестр сборок GraphRAG-сообществ. Каждая сборка описывается неизменяемой
записью :class:`BuildRecord` (версия, статус, число сообществ, отметка времени,
флаг активности). :class:`BuildRegistry` хранит упорядоченный список записей и
управляет тем, какая сборка активна: активация делает одну запись активной и
снимает активность со всех остальных (только для успешно собранных, статус
``built``); откат (:meth:`rollback`) переактивирует предыдущую успешную сборку;
обрезка (:meth:`prune`) удаляет старейшие неактивные сборки сверх лимита.

EN: Registry of GraphRAG community builds. Each build is an immutable
:class:`BuildRecord` (version, status, community count, timestamp, active flag).
:class:`BuildRegistry` holds an ordered list of records and controls which build
is active: activation marks exactly one record active and clears the flag on all
others (only for successfully-``built`` records); :meth:`rollback` re-activates
the previous successful build; :meth:`prune` deletes the oldest non-active builds
beyond a keep limit.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

STATUS_BUILT = "built"


@dataclass(frozen=True)
class BuildRecord:
    """Immutable record of a single GraphRAG community build (§11.10).

    RU: Неизменяемая запись одной сборки сообществ.
    EN: Immutable record describing one community build.
    """

    build_version: str
    status: str
    n_communities: int
    created_at: str
    active: bool

    def as_dict(self) -> dict[str, object]:
        """RU: Сериализация записи. EN: Serialise the record to a plain dict."""
        return {
            "build_version": self.build_version,
            "status": self.status,
            "n_communities": self.n_communities,
            "created_at": self.created_at,
            "active": self.active,
        }


class BuildRegistry:
    """Mutable ordered registry of :class:`BuildRecord` builds (§11.10).

    RU: Изменяемый упорядоченный реестр сборок; порядок вставки сохраняется.
    EN: Mutable ordered registry of builds; insertion order is preserved.
    """

    def __init__(self) -> None:
        """RU: Пустой реестр. EN: Start with an empty ordered record list."""
        self._records: list[BuildRecord] = []

    def register(
        self,
        build_version: str,
        n_communities: int,
        created_at: str,
        status: str = STATUS_BUILT,
    ) -> BuildRecord:
        """Register a new build (initially inactive) and return it (§11.10).

        RU: Регистрирует новую сборку в конце списка; изначально неактивна.
        Дубликат ``build_version`` запрещён. EN: Append a new build to the
        ordered list, always inactive; duplicate versions raise ``ValueError``.
        """
        if any(r.build_version == build_version for r in self._records):
            raise ValueError(f"duplicate build_version: {build_version!r}")
        record = BuildRecord(
            build_version=build_version,
            status=status,
            n_communities=n_communities,
            created_at=created_at,
            active=False,
        )
        self._records.append(record)
        return record

    def _index_of(self, build_version: str) -> int:
        """RU: Индекс записи по версии. EN: Index of the record, else raise."""
        for i, r in enumerate(self._records):
            if r.build_version == build_version:
                return i
        raise KeyError(f"unknown build_version: {build_version!r}")

    def activate(self, build_version: str) -> BuildRecord:
        """Activate one built version and clear active on all others (§11.10).

        RU: Делает указанную сборку активной и снимает активность со всех
        прочих. Активировать можно только сборку со статусом ``built`` — иначе
        ``ValueError``. EN: Marks the given build active and clears the flag on
        every other record. Only ``built`` records may be activated; otherwise a
        ``ValueError`` is raised.
        """
        idx = self._index_of(build_version)
        if self._records[idx].status != STATUS_BUILT:
            raise ValueError(
                f"cannot activate build {build_version!r} with status "
                f"{self._records[idx].status!r}; expected {STATUS_BUILT!r}"
            )
        for i, r in enumerate(self._records):
            self._records[i] = replace(r, active=(i == idx))
        return self._records[idx]

    def active_version(self) -> str | None:
        """RU: Версия активной сборки или None. EN: Active version, else None."""
        for r in self._records:
            if r.active:
                return r.build_version
        return None

    def rollback(self) -> str | None:
        """Re-activate the previous successfully-built version (§11.10).

        RU: Переактивирует предыдущую успешно собранную (``built``) версию — ту,
        что стоит раньше текущей активной в порядке вставки. Возвращает версию,
        ставшую активной, или ``None``, если откатываться некуда (нет активной
        сборки либо нет более ранней ``built``-версии).

        EN: Re-activates the most recent successfully-``built`` version that
        precedes the current active one in insertion order. Returns the newly
        active version, or ``None`` when there is nothing to roll back to (no
        active build, or no earlier ``built`` version exists).
        """
        active = self.active_version()
        if active is None:
            return None
        idx = self._index_of(active)
        for i in range(idx - 1, -1, -1):
            if self._records[i].status == STATUS_BUILT:
                target = self._records[i].build_version
                self.activate(target)
                return target
        return None

    def prune(self, keep: int) -> list[str]:
        """Delete oldest non-active builds beyond ``keep`` (§11.10).

        RU: Удаляет старейшие НЕактивные сборки, оставляя не более ``keep`` всего
        записей; активная сборка не удаляется никогда. Возвращает список
        удалённых версий в порядке удаления (от старых к новым). ``keep < 0``
        трактуется как ``0``.

        EN: Deletes the oldest non-active builds so that at most ``keep`` records
        remain, never removing the active build. Returns the removed versions in
        deletion order (oldest first). A negative ``keep`` is treated as ``0``.
        """
        keep = max(keep, 0)
        removed: list[str] = []
        # Oldest-first candidates that are safe to drop (non-active).
        for r in list(self._records):
            if len(self._records) <= keep:
                break
            if r.active:
                continue
            self._records.remove(r)
            removed.append(r.build_version)
        return removed

    def as_dict(self) -> dict[str, object]:
        """RU: Сериализация всего реестра. EN: Serialise all records to a dict."""
        return {
            "records": [r.as_dict() for r in self._records],
            "active_version": self.active_version(),
        }
