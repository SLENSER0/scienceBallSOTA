"""Eval report assembly — свести три блока метрик в один отчёт (§18.7).

Собирает три независимых блока метрик оценки в единый, сериализуемый отчёт:

* ``retrieval``  — ранжирование поиска (``kg_eval.retrieval_metrics`` /
  ``kg_eval.retrieval_eval``): ``recall_at_k`` / ``precision_at_k`` /
  ``mrr`` / ``ndcg_at_k`` и т.д. (§18.6 / §15.2).
* ``extraction`` — качество извлечения (gap/contradiction PRF из
  ``kg_eval.gap_metrics``): ``precision`` / ``recall`` / ``f1`` / ``tp`` … (§15.10).
* ``answer``     — качество ответа агента (агрегат ``kg_eval.metrics.CaseResult``:
  доля пройденных кейсов, средний entity-recall …) (§24.18).

Каждый блок — обычный ``dict`` (уже готовые ``as_dict()``-словари этих модулей —
данный модуль их только читает и НЕ импортирует, оставаясь чистым и без циклов).
:func:`build_report` склеивает блоки, дописывая происхождение (``git_sha`` +
``dataset_version``) в поле ``generated_from``. :class:`EvalReport` рендерится в
JSON (:meth:`EvalReport.to_json`) и в двуязычный Markdown с таблицами метрик
(:meth:`EvalReport.to_markdown`, секция RU/EN на каждый блок).

Pure-python: только ``json`` из stdlib. Детерминированно — одинаковый вход всегда
даёт байт-в-байт одинаковый вывод.

Assembles three independent eval metric blocks (retrieval / extraction / answer)
into one serializable :class:`EvalReport` with JSON + bilingual-Markdown renderers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Column labels for the per-block metric tables (RU/EN in one header cell).
_METRIC_HEADER = "| Metric / Метрика | Value / Значение |"
_METRIC_RULE = "| --- | --- |"
# Rendered when a block carries no metrics (empty / omitted) — keeps output valid.
_NO_METRICS = "_No metrics / Нет метрик._"

# (english heading, russian heading, attribute) for each block, render order fixed.
_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("Retrieval", "Поиск", "retrieval"),
    ("Extraction", "Извлечение", "extraction"),
    ("Answer", "Ответ", "answer"),
)


def _fmt_value(value: Any) -> str:
    """Render a leaf metric value for a Markdown table cell (§18.7).

    Booleans become JSON-style ``true``/``false``; scalars use ``str``; anything
    else (lists / nested leftovers) is compact-JSON encoded. Table-breaking ``|``
    and newlines are escaped so a cell never splits or wraps a row.
    """
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float, str)):
        text = str(value)
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _flatten(block: dict[str, Any]) -> dict[str, Any]:
    """Flatten a nested metric block to dotted keys, preserving insertion order.

    ``{"aggregate": {"mrr": 0.5}}`` → ``{"aggregate.mrr": 0.5}``. Nested ``dict``s
    recurse; every other value (scalars, lists) is a leaf. Insertion order is kept
    so the rendered table is deterministic for a given input.
    """
    flat: dict[str, Any] = {}

    def _walk(prefix: str, obj: Any) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                dotted = f"{prefix}.{key}" if prefix else str(key)
                _walk(dotted, val)
        else:
            flat[prefix] = obj

    _walk("", block)
    return flat


def _metric_table(block: dict[str, Any]) -> str:
    """Render one metric block as a Markdown table (or a graceful empty note)."""
    flat = _flatten(block)
    if not flat:
        return _NO_METRICS
    rows = [_METRIC_HEADER, _METRIC_RULE]
    rows.extend(f"| {key} | {_fmt_value(value)} |" for key, value in flat.items())
    return "\n".join(rows)


@dataclass(frozen=True)
class EvalReport:
    """Assembled eval report — три блока метрик + происхождение (§18.7).

    Собранный отчёт оценки: словари ``retrieval`` / ``extraction`` / ``answer`` и
    строка ``generated_from`` (git-sha + версия датасета). Рендерится в
    :meth:`to_json` и двуязычный :meth:`to_markdown`.
    """

    retrieval: dict[str, Any] = field(default_factory=dict)
    extraction: dict[str, Any] = field(default_factory=dict)
    answer: dict[str, Any] = field(default_factory=dict)
    generated_from: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready); block dicts are shallow-copied."""
        return {
            "retrieval": dict(self.retrieval),
            "extraction": dict(self.extraction),
            "answer": dict(self.answer),
            "generated_from": self.generated_from,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Deterministic JSON of :meth:`as_dict` (``sort_keys`` → stable order)."""
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    def to_markdown(self) -> str:
        """Bilingual (RU/EN) Markdown: a section + metric table per block (§18.7)."""
        lines: list[str] = [
            "# Eval Report / Отчёт об оценке",
            "",
            f"_Generated from / Сформировано из: {self.generated_from}_",
            "",
        ]
        for title_en, title_ru, attr in _SECTIONS:
            block: dict[str, Any] = getattr(self, attr)
            lines.append(f"## {title_en} / {title_ru}")
            lines.append("")
            lines.append(_metric_table(block))
            lines.append("")
        return "\n".join(lines)


def build_report(
    *,
    retrieval: dict[str, Any] | None = None,
    extraction: dict[str, Any] | None = None,
    answer: dict[str, Any] | None = None,
    git_sha: str = "",
    dataset_version: str = "",
) -> EvalReport:
    """Assemble the three metric blocks into one :class:`EvalReport` (§18.7).

    Собирает переданные блоки метрик (любой из них можно опустить — станет пустым
    ``{}``) в один отчёт, записывая происхождение в ``generated_from`` из
    ``git_sha`` и ``dataset_version``. Блоки поверхностно копируются, чтобы
    последующая мутация исходных словарей не меняла собранный отчёт.
    """
    generated_from = f"git_sha={git_sha}; dataset_version={dataset_version}"
    return EvalReport(
        retrieval=dict(retrieval or {}),
        extraction=dict(extraction or {}),
        answer=dict(answer or {}),
        generated_from=generated_from,
    )
