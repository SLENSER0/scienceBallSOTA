"""Experiment Explorer sortable table view-model (§17.12 / §5.2.5).

RU: Чистая view-модель сортируемой таблицы Experiment Explorer. §17.12 требует
табличное представление с сортировкой по колонкам, но ``answer_tabs`` лишь
пробрасывает строки экспериментов, а ``experiment_projection`` строит мини-граф —
ни один из них не задаёт спецификацию колонок и не сортирует. Здесь описаны девять
колонок §5.2.5 (``experiment/material/processing/property/value/unit/effect/
confidence/evidenceCount`` в этом порядке), отображение каждого конверта-эксперимента
в типизированную строку ячеек (отсутствующее поле → ``None``) и устойчивая сортировка,
при которой пустые (``None``) ячейки всегда идут последними независимо от направления.

EN: Pure sortable-table view-model for the Experiment Explorer. §17.12 asks for a
column-sortable table, but ``answer_tabs`` only passes experiment rows through and
``experiment_projection`` builds a mini-graph — neither defines a column spec or a
sort. This module owns the nine §5.2.5 columns (in fixed order), maps each envelope
experiment dict to a typed cell row (missing field → ``None``) and sorts rows stably
with ``None`` cells always last regardless of direction.

- **build_experiment_table** — конверты → колонки+строки / envelopes → columns+rows.
- **sort_rows** — устойчивая сортировка, ``None`` в конец / stable sort, None last.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# §5.2.5 nine Experiment Explorer columns, in fixed order (key, label, type).
COLUMNS: tuple[dict[str, str], ...] = (
    {"key": "experiment", "label": "Experiment", "type": "string"},
    {"key": "material", "label": "Material", "type": "string"},
    {"key": "processing", "label": "Processing", "type": "string"},
    {"key": "property", "label": "Property", "type": "string"},
    {"key": "value", "label": "Value", "type": "number"},
    {"key": "unit", "label": "Unit", "type": "string"},
    {"key": "effect", "label": "Effect", "type": "string"},
    {"key": "confidence", "label": "Confidence", "type": "number"},
    {"key": "evidenceCount", "label": "Evidence Count", "type": "integer"},
)

# Ordered column keys, derived once from the single COLUMNS source of truth.
_COLUMN_KEYS: tuple[str, ...] = tuple(col["key"] for col in COLUMNS)


@dataclass(frozen=True)
class ExperimentTable:
    """Frozen §17.12 sortable-table view-model / неизменяемая view-модель таблицы.

    - ``columns`` — спецификация девяти колонок §5.2.5 / the nine §5.2.5 column specs.
    - ``rows`` — по одной типизированной строке ячеек на эксперимент / one typed
      cell row per experiment (each row keyed by the COLUMNS keys, missing → ``None``).
    """

    columns: tuple[dict, ...]
    rows: tuple[dict, ...]

    def as_dict(self) -> dict[str, Any]:
        """Plain-mapping projection for the UI / trace round-trip (§17.12)."""
        return {
            "columns": [dict(col) for col in self.columns],
            "rows": [dict(row) for row in self.rows],
        }


def build_experiment_table(experiments: list[dict]) -> ExperimentTable:
    """Map envelope experiment dicts → §5.2.5 columns + typed cell rows (§17.12).

    RU: Каждый конверт превращается в строку с ровно девятью ячейками (ключи из
    ``COLUMNS``); отсутствующее поле даёт ``None`` — ``value``/``unit`` и прочие
    известные поля проходят насквозь. EN: Each envelope becomes a row of exactly the
    nine ``COLUMNS`` cells; a missing field yields ``None`` while known fields
    (``value``/``unit``/...) pass straight through.
    """
    rows = tuple({key: experiment.get(key) for key in _COLUMN_KEYS} for experiment in experiments)
    return ExperimentTable(columns=COLUMNS, rows=rows)


def sort_rows(rows: Sequence[dict], key: str, *, descending: bool = False) -> list[dict]:
    """Stably sort ``rows`` by column ``key``; ``None`` cells always last (§17.12).

    RU: Устойчивая сортировка (порядок равных ключей сохраняется). Ячейки со значением
    ``None`` всегда идут последними — как при возрастании, так и при убывании. Ключ,
    отсутствующий в ``COLUMNS``, — ошибка. EN: Stable sort (equal keys keep original
    order). ``None`` cells sort last under both ascending and descending. A ``key`` not
    in ``COLUMNS`` raises ``ValueError``.
    """
    if key not in _COLUMN_KEYS:
        raise ValueError(f"unknown sort column: {key!r} (not in COLUMNS)")
    present = [row for row in rows if row.get(key) is not None]
    absent = [row for row in rows if row.get(key) is None]
    present.sort(key=lambda row: row[key], reverse=descending)
    return present + absent
