"""Before/after diff of a curation event (§16.8): полевой diff свойств узла/ребра.

Курирующее событие переводит сущность из состояния `before` в `after` (те же
property-map'ы, что фигурируют в :mod:`kg_common.storage.decisions` как
`before_hash`/`after_hash`, только развёрнутые в dict). Этот модуль — чистый
Python без стора: он сравнивает два словаря свойств и выдаёт полевой
(field-level) diff — какие поля добавлены, удалены, изменены (со старым→новым
значением) и какие остались прежними.

Diff — «плоский» по ключам верхнего уровня: вложенное значение (dict/list)
сравнивается целиком, поэтому смена вложенного поля видна как изменение
соответствующего верхнеуровневого ключа (старый dict → новый dict).

RU/EN: изменение / diff, добавлено / added, удалено / removed, изменено /
changed, без изменений / unchanged, пусто-нет-изменений / no-op.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CurationDiff:
    """Полевой diff двух property-map'ов сущности (§16.8).

    `added` — ключи только в `after` (ключ → новое значение); `removed` — ключи
    только в `before` (ключ → старое значение); `changed` — общие ключи с
    различными значениями (ключ → кортеж ``(old, new)``, старое→новое);
    `unchanged_keys` — отсортированный список общих ключей с равными значениями.
    """

    added: dict[str, Any]
    removed: dict[str, Any]
    changed: dict[str, tuple[Any, Any]]
    unchanged_keys: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/audit-лога)."""
        return asdict(self)


def diff_states(before: dict[str, Any], after: dict[str, Any]) -> CurationDiff:
    """Построить полевой diff перехода `before` → `after` (§16.8).

    Оба аргумента — property-map'ы (dict) узла или ребра. Ключи каждой секции
    отсортированы для детерминированного вывода. Значения сравниваются оператором
    ``==``; вложенные dict/list сравниваются целиком (плоский по верхним ключам).
    """
    before_keys = set(before)
    after_keys = set(after)
    common = before_keys & after_keys

    added = {k: after[k] for k in sorted(after_keys - before_keys)}
    removed = {k: before[k] for k in sorted(before_keys - after_keys)}
    changed = {k: (before[k], after[k]) for k in sorted(common) if before[k] != after[k]}
    unchanged_keys = [k for k in sorted(common) if before[k] == after[k]]

    return CurationDiff(
        added=added,
        removed=removed,
        changed=changed,
        unchanged_keys=unchanged_keys,
    )


def is_noop(diff: CurationDiff) -> bool:
    """``True``, если переход ничего не менял (нет added/removed/changed).

    Наличие `unchanged_keys` не влияет: одинаковые значения — это и есть no-op.
    """
    return not (diff.added or diff.removed or diff.changed)


def summarize_diff(diff: CurationDiff) -> str:
    """Человекочитаемая RU/EN сводка diff'а (для UI/лога, §16.8).

    Всегда начинается со счётчиков ``+доб / -удал / ~изм / =без-изм``; далее —
    перечисление затронутых полей. Изменённое поле выводится как
    ``ключ: старое→новое``, поэтому имя изменённого поля всегда упомянуто.
    """
    parts = [
        f"Диф/Diff: +{len(diff.added)} доб/added / -{len(diff.removed)} удал/removed / "
        f"~{len(diff.changed)} изм/changed / ={len(diff.unchanged_keys)} без-изм/unchanged"
    ]
    if diff.added:
        parts.append("Добавлены/Added: " + ", ".join(f"{k}={v!r}" for k, v in diff.added.items()))
    if diff.removed:
        parts.append("Удалены/Removed: " + ", ".join(f"{k}={v!r}" for k, v in diff.removed.items()))
    if diff.changed:
        parts.append(
            "Изменены/Changed: "
            + ", ".join(f"{k}: {old!r}→{new!r}" for k, (old, new) in diff.changed.items())
        )
    return "; ".join(parts)
