"""Golden dataset category quota validator (§18.6).

Проверяет золотой набор вопросов на соответствие квотам по категориям из §15.1
и на уникальность идентификаторов. Существующие ``golden.py`` / ``golden_builder.py``
загружают набор, но не следят за квотами — этот модуль закрывает пробел.
:func:`count_categories` считает вопросы по полю ``category`` (включая незнакомые
категории), :func:`check_quota` собирает :class:`QuotaReport`: чего не хватает до
квоты (``missing``), где перебор (``surplus``), какие ``id`` повторяются
(``duplicate_ids``) и итог ``ok`` (нет недобора и нет дублей).

Validates a golden question set against the §15.1 per-category quotas plus id
uniqueness. :func:`count_categories` tallies items by their ``category`` field
(unknown categories included); :func:`check_quota` returns a frozen
:class:`QuotaReport` with under-quota categories (``missing``), over-quota extras
(``surplus``), repeated ids (``duplicate_ids``) and ``ok`` (no missing, no dupes).

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# §15.1 required question counts per category. Ключ — категория, значение — квота.
REQUIRED_QUOTAS: dict[str, int] = {
    "material_regime_property": 20,
    "experiment_lookup": 15,
    "evidence": 10,
    "gap": 10,
    "contradiction": 10,
    "broad_summary": 10,
}


@dataclass(frozen=True)
class QuotaReport:
    """Итог проверки квот золотого набора (§18.6).

    ``counts`` — фактические счётчики по всем встреченным категориям (в т.ч. вне
    квоты); ``missing`` — категории с недобором; ``surplus`` — перебор сверх квоты
    по категориям; ``duplicate_ids`` — повторяющиеся ``id``; ``ok`` истинно, когда
    нет недобора и нет дублей (перебор сам по себе не роняет ``ok``).

    Quota-check result: ``ok`` is true iff there are no missing categories and no
    duplicate ids; surplus alone does not fail the report.
    """

    counts: dict[str, int]
    missing: tuple[str, ...]
    surplus: dict[str, int]
    duplicate_ids: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view suitable for JSON / logging."""
        return {
            "counts": dict(self.counts),
            "missing": list(self.missing),
            "surplus": dict(self.surplus),
            "duplicate_ids": list(self.duplicate_ids),
            "ok": self.ok,
        }


def count_categories(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Tally items by their ``category`` field, unknown categories included.

    Считает вопросы по категориям; категории вне квоты тоже попадают в результат.
    """
    counts: Counter[str] = Counter()
    for item in items:
        counts[item["category"]] += 1
    return dict(counts)


def check_quota(
    items: Iterable[Mapping[str, Any]],
    quotas: Mapping[str, int] = REQUIRED_QUOTAS,
) -> QuotaReport:
    """Validate ``items`` against ``quotas`` and id uniqueness (§18.6).

    Материализует вход один раз (чтобы посчитать и категории, и ``id``), затем
    формирует :class:`QuotaReport`. ``missing`` — категории под квотой, ``surplus``
    — перебор сверх квоты, ``duplicate_ids`` — повторяющиеся ``id`` в порядке
    первого повторения. ``ok`` = нет недобора и нет дублей.
    """
    materialized = list(items)
    counts = count_categories(materialized)

    missing: list[str] = []
    surplus: dict[str, int] = {}
    for category, quota in quotas.items():
        have = counts.get(category, 0)
        if have < quota:
            missing.append(category)
        elif have > quota:
            surplus[category] = have - quota

    id_counts: Counter[str] = Counter()
    for item in materialized:
        if "id" in item:
            id_counts[item["id"]] += 1
    duplicate_ids = tuple(_id for _id, n in id_counts.items() if n > 1)

    ok = not missing and not duplicate_ids
    return QuotaReport(
        counts=counts,
        missing=tuple(missing),
        surplus=surplus,
        duplicate_ids=duplicate_ids,
        ok=ok,
    )
