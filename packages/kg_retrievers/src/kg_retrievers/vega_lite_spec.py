"""Vega-Lite v5 chart spec builder — embeddable analytics (§22 reporting).

Строитель спецификаций Vega-Lite. This module turns plain *row data* — the kind
of ``list[dict]`` produced by coverage / gap / metric reporters — into a
self-contained `Vega-Lite v5 <https://vega.github.io/vega-lite/>`_ JSON chart
specification. A caller can embed the resulting dict directly in a web page (via
``vegaEmbed``) or serialise it with :func:`to_json` for an API payload.

No other module in the codebase emits chart specs, so this is the single source of
truth for the shape of an embeddable chart. It is deliberately *pure* — it neither
touches the graph nor performs any I/O; it only reshapes rows into a spec.

Two chart kinds are supported:

- :func:`bar_chart` — a bar mark over a categorical *x* (e.g. property name) and a
  quantitative *y* (e.g. coverage count). Typical for coverage / gap tables.
- :func:`scatter_chart` — a point mark over two quantitative fields with an optional
  ``color`` encoding (e.g. a metric-vs-metric plot coloured by community).

The immutable :class:`VegaLiteSpec` carries the four load-bearing pieces (``mark``,
``encoding``, ``data_values``, ``title``); :meth:`VegaLiteSpec.as_dict` assembles
them into the full Vega-Lite object with the ``$schema`` pin. A ``title`` of
``None`` is omitted from the output entirely (Vega-Lite treats a missing ``title``
as "no title", which is exactly the intent).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# Vega-Lite v5 schema URL — the pin that makes ``as_dict()`` a valid v5 spec.
VEGA_LITE_V5_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"


@dataclass(frozen=True)
class VegaLiteSpec:
    """One immutable Vega-Lite v5 chart specification (§22).

    ``mark`` is the Vega-Lite mark type (``"bar"`` / ``"point"``); ``encoding`` is the
    channel-to-field mapping; ``data_values`` is the inlined row data (кортеж строк);
    ``title`` is an optional chart title (``None`` omits the key from :meth:`as_dict`).
    """

    mark: str
    encoding: dict
    data_values: tuple[dict, ...]
    title: str | None

    def as_dict(self) -> dict:
        """Return the full Vega-Lite v5 dict (``$schema`` / ``data`` / ``mark`` / …).

        The ``title`` key is present only when :attr:`title` is not ``None``.
        """
        spec: dict = {
            "$schema": VEGA_LITE_V5_SCHEMA,
            "data": {"values": [dict(row) for row in self.data_values]},
            "mark": self.mark,
            "encoding": dict(self.encoding),
        }
        if self.title is not None:
            spec["title"] = self.title
        return spec


def bar_chart(
    rows: list[dict],
    *,
    x: str,
    y: str,
    x_type: str = "nominal",
    y_type: str = "quantitative",
    title: str | None = None,
) -> VegaLiteSpec:
    """Build a bar-mark spec over categorical *x* / quantitative *y* (§22).

    ``x`` / ``y`` are field names present in every row; ``x_type`` / ``y_type`` are the
    Vega-Lite measurement types for those channels. Столбчатая диаграмма.
    """
    encoding = {
        "x": {"field": x, "type": x_type},
        "y": {"field": y, "type": y_type},
    }
    return VegaLiteSpec(
        mark="bar",
        encoding=encoding,
        data_values=tuple(rows),
        title=title,
    )


def scatter_chart(
    rows: list[dict],
    *,
    x: str,
    y: str,
    color: str | None = None,
    title: str | None = None,
) -> VegaLiteSpec:
    """Build a point-mark scatter spec over quantitative *x* / *y* (§22).

    When ``color`` is given it adds a nominal ``color`` encoding channel; when it is
    ``None`` the ``color`` key is absent. Диаграмма рассеяния.
    """
    encoding: dict = {
        "x": {"field": x, "type": "quantitative"},
        "y": {"field": y, "type": "quantitative"},
    }
    if color is not None:
        encoding["color"] = {"field": color, "type": "nominal"}
    return VegaLiteSpec(
        mark="point",
        encoding=encoding,
        data_values=tuple(rows),
        title=title,
    )


def to_json(spec: VegaLiteSpec) -> str:
    """Serialise ``spec`` to a stable JSON string (``json.dumps`` with sorted keys)."""
    return json.dumps(spec.as_dict(), sort_keys=True)
