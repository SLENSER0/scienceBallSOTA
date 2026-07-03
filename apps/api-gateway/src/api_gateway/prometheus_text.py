"""Prometheus text exposition for ``GET /admin/metrics`` (§14.11).

Чистый stdlib-рендер формата экспозиции Prometheus поверх неизменяемых
:class:`Sample` / :class:`MetricFamily`. :func:`escape_label_value` экранирует
обратную косую черту, двойную кавычку и перевод строки в значениях меток;
:func:`render_family` печатает строки ``# HELP`` и ``# TYPE`` и затем сэмплы;
:func:`render_exposition` склеивает семейства и всегда завершается переводом
строки. Целочисленные значения печатаются без десятичной точки. Модуль
дополняет ``observability.py`` (тот считает только перцентили и не умеет
сериализовать формат экспозиции).

Pure-stdlib Prometheus text-exposition renderer over frozen :class:`Sample` /
:class:`MetricFamily`. :func:`escape_label_value` escapes backslash, double
quote and newline in label values; :func:`render_family` emits the ``# HELP``
and ``# TYPE`` lines followed by the samples; :func:`render_exposition` joins
families and always ends with a trailing newline. Integer-valued floats are
printed without a decimal point. This complements ``observability.py`` (which
only computes percentiles and has no exposition-format writer).

* :class:`Sample`         — one metric line: name, value and optional labels.
* :class:`MetricFamily`   — name/type/help plus a tuple of :class:`Sample`.
* :func:`escape_label_value` — label-value escaping per the text format.
* :func:`render_family`   — a single family as ``# HELP``/``# TYPE`` + samples.
* :func:`render_exposition` — a full exposition body ending with ``\\n``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Sample:
    """Одна строка метрики: имя, значение и (опционально) метки (§14.11).

    One metric line. ``labels`` maps label name to value; an empty mapping (the
    default) renders the bare ``name value`` form without braces.
    """

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Сэмпл как ``{name, value, labels}`` / wire form (§14.11)."""
        return {"name": self.name, "value": self.value, "labels": dict(self.labels)}


@dataclass(frozen=True, slots=True)
class MetricFamily:
    """Семейство метрик: имя, тип, справка и кортеж сэмплов (§14.11).

    Metric family. ``type`` is a Prometheus metric type (``counter``, ``gauge``,
    ``histogram`` …); ``help`` is the human-readable description; ``samples``
    are the individual :class:`Sample` lines that belong to this family.
    """

    name: str
    type: str
    help: str
    samples: tuple[Sample, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Семейство как ``{name, type, help, samples}`` / wire form (§14.11)."""
        return {
            "name": self.name,
            "type": self.type,
            "help": self.help,
            "samples": [s.as_dict() for s in self.samples],
        }


def escape_label_value(s: str) -> str:
    """Экранировать значение метки: ``\\``, ``"`` и перевод строки (§14.11).

    Escape a label value for the text format: backslash first, then double
    quote, then newline (order matters so backslashes are not double-escaped).
    """
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_value(value: float) -> str:
    """Число как текст: целые — без точки, спецзначения — ``+Inf``/``NaN``."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if value == int(value):
        return str(int(value))
    return repr(value)


def _render_labels(labels: dict[str, str]) -> str:
    """Собрать ``{k="v",…}`` из меток (отсортировано) или пустую строку."""
    if not labels:
        return ""
    inner = ",".join(f'{k}="{escape_label_value(v)}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


def _render_sample(sample: Sample) -> str:
    """Одна строка сэмпла ``name{labels} value`` без завершающего ``\\n``."""
    return f"{sample.name}{_render_labels(dict(sample.labels))} {_format_value(sample.value)}"


def render_family(fam: MetricFamily) -> str:
    """Отрендерить семейство: ``# HELP``, ``# TYPE`` и сэмплы (§14.11).

    Emit the ``# HELP <name> <help>`` and ``# TYPE <name> <type>`` header lines
    followed by one line per sample. The returned string ends with a newline.
    """
    lines = [f"# HELP {fam.name} {fam.help}", f"# TYPE {fam.name} {fam.type}"]
    lines.extend(_render_sample(s) for s in fam.samples)
    return "\n".join(lines) + "\n"


def render_exposition(families: list[MetricFamily]) -> str:
    """Склеить семейства в тело экспозиции; всегда с ``\\n`` в конце (§14.11).

    Join rendered families into a full exposition body. Each family already ends
    with a newline, so the whole document ends with a trailing newline too.
    """
    return "".join(render_family(fam) for fam in families)
