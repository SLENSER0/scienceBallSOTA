"""Graph snapshot lineage & restore-point selection (§16.10).

`GraphSnapshot` DTO и diff-движок уже есть, но никто не проходит цепочку
родителей снапшотов и не выбирает точку восстановления (restore point).
§16.10 трактует каждый снапшот как коммит, ссылающийся на своего
предшественника через `parent_id` (как git-commit → parent).

Этот модуль — чистый Python без стора:

- :func:`build_chain` связывает снапшоты по `parent_id`, начиная с самой
  свежей «головы» (head) и идя назад к корню (root, `parent_id is None`);
  порядок `order` — от новейшего к старейшему. Снапшоты, чей `parent_id`
  ссылается на отсутствующий id, собираются в `broken` (разрыв цепочки).
- :func:`restore_point` выбирает id новейшего снапшота с
  ``created_at <= at_iso`` — точку восстановления «на момент времени».

RU/EN: снапшот / snapshot, цепочка / chain, голова / head, корень / root,
родитель / parent, разрыв / broken, точка восстановления / restore point,
порядок / order (новейший→старейший / newest→oldest).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SnapshotChain:
    """Линеаризованная цепочка снапшотов (§16.10).

    `head` — id самого свежего снапшота (голова цепочки); `order` — список id
    от новейшего к старейшему (newest→oldest), пройденный по `parent_id`;
    `broken` — id снапшотов, чей `parent_id` указывает на отсутствующий
    (не переданный) снапшот, то есть разрывает цепочку.
    """

    head: str
    order: list[str]
    broken: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/audit-лога)."""
        return asdict(self)


def _created_at(snapshot: Mapping[str, Any]) -> str:
    """ISO-время создания снапшота (`created_at`) как строка для сравнения."""
    return str(snapshot["created_at"])


def build_chain(snapshots: Sequence[Mapping[str, Any]]) -> SnapshotChain:
    """Построить цепочку снапшотов по `parent_id`, от головы к корню (§16.10).

    Каждый снапшот — mapping с `id`/`parent_id`/`created_at`. Голова (head) —
    снапшот с максимальным `created_at`. От головы цепочка идёт назад по
    `parent_id` до корня (`parent_id is None`); `order` перечисляет id
    новейший→старейший. Корневой снапшот завершает цепочку и НЕ попадает в
    `broken`. Любой снапшот, чей `parent_id` ссылается на id, которого нет
    среди переданных, добавляется в `broken` (разрыв). При пустом входе —
    пустая цепочка (``head == ""``).
    """
    if not snapshots:
        return SnapshotChain(head="", order=[], broken=[])

    by_id: dict[str, Mapping[str, Any]] = {str(s["id"]): s for s in snapshots}

    # Голова — снапшот с максимальным created_at (при равенстве — по id).
    head_snapshot = max(snapshots, key=lambda s: (_created_at(s), str(s["id"])))
    head_id = str(head_snapshot["id"])

    order: list[str] = []
    seen: set[str] = set()
    current: str | None = head_id
    while current is not None and current in by_id and current not in seen:
        order.append(current)
        seen.add(current)
        parent = by_id[current].get("parent_id")
        current = None if parent is None else str(parent)

    # `broken`: parent_id указывает на отсутствующий снапшот (не root, не known).
    broken: list[str] = []
    for snapshot in snapshots:
        parent = snapshot.get("parent_id")
        if parent is not None and str(parent) not in by_id:
            broken.append(str(snapshot["id"]))
    broken.sort()

    return SnapshotChain(head=head_id, order=order, broken=broken)


def restore_point(snapshots: Sequence[Mapping[str, Any]], at_iso: str) -> str | None:
    """Выбрать точку восстановления «на момент времени» (§16.10).

    Возвращает id новейшего снапшота с ``created_at <= at_iso`` (граница
    включительно: равенство `created_at == at_iso` подходит). Если ни один
    снапшот не создан на момент `at_iso` или раньше — ``None``.
    """
    candidates = [s for s in snapshots if _created_at(s) <= at_iso]
    if not candidates:
        return None
    best = max(candidates, key=lambda s: (_created_at(s), str(s["id"])))
    return str(best["id"])
