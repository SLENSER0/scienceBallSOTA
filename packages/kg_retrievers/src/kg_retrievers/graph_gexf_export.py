"""Graph export to GEXF 1.3 (Gephi) для визуализации графа знаний (§22.6).

Чистый stdlib-сериализатор (только :func:`xml.sax.saxutils.escape` для экранирования)
без доступа к графу/БД/LLM/часам: на вход — обычные ``dict`` узлов/рёбер (уже
прочитанные из графа), на выход — GEXF 1.3 XML-документ, который открывается в
Gephi. Документ несёт ``<attributes class="node">`` блок, объявляющий колонки
свойств узлов, и на каждый узел — ``<attvalue>`` записи с их значениями.

Тип свойства (GEXF) выводится из первого встреченного значения:
``bool → boolean``, ``int → integer``, ``float → double``, иначе ``string``
(``bool`` проверяется раньше ``int``, так как он его подкласс). Порядок колонок —
детерминированный «first-seen»: как свойства впервые встречаются при обходе узлов.

Kuzu note: custom node props are NOT queryable columns — a retriever must RETURN base
columns and read the rest via ``get_node``; к моменту, когда узел/ребро ``dict``
доходит сюда, он уже несёт слитые свойства, поэтому этот модуль не трогает store.

Entry points:

- :func:`declare_attributes` — first-seen колонки ``(name, gexf_type)`` по узлам;
- :func:`to_gexf` — собрать :class:`GexfDoc` (колонки + XML) для узлов/рёбер;
- :func:`gexf_document` — краткая обёртка, возвращающая только XML-строку.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

# GEXF namespace/version, зафиксированные так, чтобы вывод был hand-checkable (§22.6).
_GEXF_NS = "http://gexf.net/1.3"
_GEXF_VERSION = "1.3"

# Ключи узла, не являющиеся свойствами-колонками: id/имя/метка и вложенный blob.
_RESERVED_NODE_KEYS: frozenset[str] = frozenset({"id", "name", "label", "properties"})

# Кандидаты ключей для источника/цели ребра (первый непустой выигрывает).
_SOURCE_KEYS: tuple[str, ...] = ("source", "from", "src", "start")
_TARGET_KEYS: tuple[str, ...] = ("target", "to", "dst", "end")


def _gexf_type(value: Any) -> str:
    """GEXF-тип значения: boolean/integer/double/string (bool раньше int)."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double"
    return "string"


def _fmt_value(value: Any) -> str:
    """Строковое значение для ``<attvalue>``: bool → ``true``/``false``, иначе ``str``."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _attr(value: str) -> str:
    """Экранировать значение XML-атрибута (``&``, ``<``, ``>`` и двойную кавычку)."""
    return escape(value, {'"': "&quot;"})


def _node_prop_map(node: Mapping[str, Any]) -> dict[str, Any]:
    """Свойства-колонки узла (без зарезервированных / ``None``), first-seen порядок.

    Сначала верхнеуровневые ключи, затем вложенный ``properties`` dict; при коллизии
    первое вхождение выигрывает (``setdefault``). ``dict`` сохраняет порядок вставки,
    поэтому итерация по результату даёт детерминированный first-seen порядок.
    """
    props: dict[str, Any] = {}
    for key, value in node.items():
        if key in _RESERVED_NODE_KEYS or value is None:
            continue
        props.setdefault(key, value)
    inner = node.get("properties")
    if isinstance(inner, Mapping):
        for key, value in inner.items():
            if key in _RESERVED_NODE_KEYS or value is None:
                continue
            props.setdefault(key, value)
    return props


def _node_id(node: Mapping[str, Any]) -> str:
    """Идентификатор узла как строка (``id`` → ``str``, иначе пустая строка)."""
    return str(node.get("id") or "")


def _node_label(node: Mapping[str, Any]) -> str:
    """Отображаемая метка узла: ``name`` → ``label`` → ``id`` (первое непустое)."""
    for key in ("name", "label"):
        value = node.get(key)
        if value:
            return str(value)
    return _node_id(node)


def _first(edge: Mapping[str, Any], keys: Sequence[str]) -> str:
    """Первое непустое значение среди ``keys`` в ``edge``, приведённое к ``str``."""
    for key in keys:
        value = edge.get(key)
        if value:
            return str(value)
    return ""


def declare_attributes(nodes: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """First-seen колонки свойств узлов как ``(name, gexf_type)`` пары (§22.6).

    Проходит ``nodes`` по порядку; для каждого узла — его свойства-колонки в порядке
    вставки. Имя добавляется при первом появлении, а его тип фиксируется по первому
    встреченному значению (:func:`_gexf_type`). Порядок результата детерминирован:
    свойства следуют в том порядке, в котором впервые встречены при обходе узлов.
    """
    types: dict[str, str] = {}
    order: list[str] = []
    for node in nodes:
        for name, value in _node_prop_map(node).items():
            if name not in types:
                types[name] = _gexf_type(value)
                order.append(name)
    return [(name, types[name]) for name in order]


@dataclass(frozen=True)
class GexfDoc:
    """GEXF 1.3 документ: объявленные колонки узлов и сериализованный XML (§22.6)."""

    attr_columns: tuple[tuple[str, str], ...]
    xml: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict: колонки как ``(name, type)`` пары + XML."""
        return {
            "attr_columns": [(name, gtype) for name, gtype in self.attr_columns],
            "xml": self.xml,
        }


def to_gexf(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    mode: str = "static",
) -> GexfDoc:
    """Сериализовать узлы/рёбра в :class:`GexfDoc` (GEXF 1.3, §22.6).

    Колонки объявляются :func:`declare_attributes` (first-seen). Документ несёт
    ``<attributes class="node">`` блок; каждый узел — ``<node id=.. label=..>`` с
    ``name`` в качестве метки и ``<attvalue for=.. value=..>`` для присутствующих у
    него свойств. Каждое ребро получает целочисленный ``id`` (0,1,2,…) и атрибуты
    ``source``/``target``. Всё текстовое экранируется (``<`` → ``&lt;``). ``mode``
    задаёт ``<graph mode=..>`` (по умолчанию ``static``). Детерминирован: без часов и
    сортировок — порядок входа сохраняется.
    """
    columns = declare_attributes(nodes)
    col_index = {name: idx for idx, (name, _t) in enumerate(columns)}

    lines: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(f'<gexf xmlns="{_GEXF_NS}" version="{_GEXF_VERSION}">')
    lines.append(f'  <graph mode="{_attr(mode)}" defaultedgetype="directed">')

    lines.append('    <attributes class="node" mode="static">')
    for idx, (name, gtype) in enumerate(columns):
        lines.append(f'      <attribute id="{idx}" title="{_attr(name)}" type="{gtype}"/>')
    lines.append("    </attributes>")

    lines.append("    <nodes>")
    for node in nodes:
        node_id = _attr(_node_id(node))
        label = _attr(_node_label(node))
        props = _node_prop_map(node)
        attvals = [(col_index[name], props[name]) for name, _t in columns if name in props]
        if attvals:
            lines.append(f'      <node id="{node_id}" label="{label}">')
            lines.append("        <attvalues>")
            for fid, value in attvals:
                val = _attr(_fmt_value(value))
                lines.append(f'          <attvalue for="{fid}" value="{val}"/>')
            lines.append("        </attvalues>")
            lines.append("      </node>")
        else:
            lines.append(f'      <node id="{node_id}" label="{label}"/>')
    lines.append("    </nodes>")

    lines.append("    <edges>")
    for idx, edge in enumerate(edges):
        source = _attr(_first(edge, _SOURCE_KEYS))
        target = _attr(_first(edge, _TARGET_KEYS))
        lines.append(f'      <edge id="{idx}" source="{source}" target="{target}"/>')
    lines.append("    </edges>")

    lines.append("  </graph>")
    lines.append("</gexf>")
    xml = "\n".join(lines) + "\n"
    return GexfDoc(attr_columns=tuple(columns), xml=xml)


def gexf_document(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> str:
    """Краткая обёртка над :func:`to_gexf`, возвращающая только XML-строку (§22.6)."""
    return to_gexf(nodes, edges).xml
