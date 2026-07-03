"""Curation-vs-ingestion diff attribution (§16.10): чей это change — куратор или ingest.

Граф-diff даёт список change-записей (каждая с `target_id` — узел/ребро, которое
изменилось). Отдельно есть поток CurationEvent'ов (каждый с `target_id` и
`created_at`). Модуль атрибутирует каждую change-запись одному из двух источников:

- *curation* — существует CurationEvent с тем же `target_id`, чей `created_at`
  попадает в инклюзивное окно ``[from, to]`` (границы включены);
- *ingestion* — иначе (события нет вовсе, либо оно вне окна).

Чистый Python без стора: сравнение строковых ISO-таймстемпов лексикографически
корректно для одинакового формата (UTC, фиксированная ширина).

RU/EN: атрибуция / attribution, курирование / curation, инжест / ingestion,
окно / window, доля / ratio.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AttributedDiff:
    """Разбиение change-записей на курирование и инжест (§16.10).

    `curation` — change-записи, объяснённые in-window CurationEvent'ом; `ingestion`
    — все прочие; `counts` — сводка ``{'curation': n, 'ingestion': m, 'total': n+m}``.
    """

    curation: list[dict]
    ingestion: list[dict]
    counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/audit-лога)."""
        return asdict(self)


def _in_window(created_at: Any, window: tuple[str, str]) -> bool:
    """``True``, если `created_at` попадает в инклюзивное окно ``[from, to]``.

    Границы включены; сравнение строковое (лексикографическое) при едином формате.
    """
    if created_at is None:
        return False
    lo, hi = window
    return lo <= str(created_at) <= hi


def attribute_changes(
    changes: Sequence[Mapping],
    events: Sequence[Mapping],
    window: tuple[str, str],
) -> AttributedDiff:
    """Атрибутировать граф-diff change-записи курированию либо инжесту (§16.10).

    `changes` — записи graph-diff, у каждой ключ `target_id`. `events` — поток
    CurationEvent'ов с ключами `target_id` и `created_at`. Change считается
    *curation*, если у его `target_id` есть хотя бы одно событие с `created_at` в
    инклюзивном окне ``[from, to]``; иначе — *ingestion*.
    """
    in_window_targets: set[Any] = {
        ev.get("target_id") for ev in events if _in_window(ev.get("created_at"), window)
    }

    curation: list[dict] = []
    ingestion: list[dict] = []
    for change in changes:
        if change.get("target_id") in in_window_targets:
            curation.append(dict(change))
        else:
            ingestion.append(dict(change))

    n = len(curation)
    m = len(ingestion)
    counts = {"curation": n, "ingestion": m, "total": n + m}
    return AttributedDiff(curation=curation, ingestion=ingestion, counts=counts)


def curation_ratio(result: AttributedDiff) -> float:
    """Доля курирования: ``curation / total`` (0.0 при ``total == 0``)."""
    total = result.counts["total"]
    if total == 0:
        return 0.0
    return result.counts["curation"] / total
