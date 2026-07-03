"""Graph export to Cytoscape SIF (Simple Interaction Format) — §22.6.

Чистый stdlib-сериализатор без доступа к графу/БД/LLM/часам: на вход — обычные
``dict`` рёбер (уже прочитанные из графа), на выход — SIF-текст, который читает
Cytoscape. SIF-строка — это ``source<TAB>relation<TAB>target1<TAB>target2...``:
все цели (targets), делящие одну пару ``(source, relation)``, собираются в одну
строку, поэтому формат компактный и hand-checkable.

Pure stdlib SIF exporter with no graph/DB/LLM/clock access: it takes plain edge
``dict``s (already read from the graph) and returns SIF text that Cytoscape reads.
A SIF line is ``source<TAB>relation<TAB>target1<TAB>target2...``: every target
sharing one ``(source, relation)`` pair is grouped onto a single row.

Kuzu note: custom node props are NOT queryable columns — a retriever must RETURN
base columns and read the rest via ``get_node``; к моменту, когда ребро ``dict``
доходит сюда, оно уже несёт нужные поля, поэтому этот модуль не трогает store.

Entry points:

- :class:`SifLine` — одна SIF-строка ``(source, relation, targets)``;
- :func:`group_edges` — сгруппировать рёбра в :class:`SifLine` (first-seen order);
- :func:`to_sif` — собрать весь SIF-текст (строки через ``\\n``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# SIF field separator — единственный разделитель формата (§22.6).
_TAB = "\t"

# Кандидаты ключей источника/отношения/цели ребра (первый непустой выигрывает).
# Candidate keys for edge source/relation/target (first non-empty wins).
_SOURCE_KEYS: tuple[str, ...] = ("source", "from", "src", "start")
_RELATION_KEYS: tuple[str, ...] = ("relation", "rel", "type", "label")
_TARGET_KEYS: tuple[str, ...] = ("target", "to", "dst", "end")


@dataclass(frozen=True, slots=True)
class SifLine:
    """Одна SIF-строка: ``source<TAB>relation<TAB>target...`` (§22.6).

    ``source`` и ``relation`` задают группу; ``targets`` — все цели этой группы в
    порядке первого появления. ``source`` and ``relation`` key the group; ``targets``
    holds every target of that group in first-seen order.
    """

    source: str
    relation: str
    targets: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """JSON-представление; ``targets`` — список (list), не кортеж."""
        return {
            "source": self.source,
            "relation": self.relation,
            "targets": list(self.targets),
        }

    def render(self) -> str:
        """Собрать строку ``source<TAB>relation<TAB>target1<TAB>target2...``."""
        return _TAB.join((self.source, self.relation, *self.targets))


def _first(edge: Sequence, keys: tuple[str, ...]) -> str:
    """Первое непустое значение среди ``keys`` в ``edge``, приведённое к ``str``.

    First non-empty value among ``keys`` in ``edge``, coerced to ``str`` (``""`` if
    none matches).
    """
    for key in keys:
        value = edge.get(key)
        if value is not None and value != "":
            return str(value)
    return ""


def group_edges(edges: Sequence[dict]) -> list[SifLine]:
    """Сгруппировать рёбра в :class:`SifLine` по ``(source, relation)`` (§22.6).

    Порядок ключей — стабильный «first-seen»: пара впервые встреченная раньше идёт
    раньше в результате. Цели в группе тоже сохраняют порядок первого появления.
    Keys keep stable first-seen order; targets within a group keep first-seen order.
    """
    order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[str]] = {}
    for edge in edges:
        source = _first(edge, _SOURCE_KEYS)
        relation = _first(edge, _RELATION_KEYS)
        target = _first(edge, _TARGET_KEYS)
        key = (source, relation)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(target)
    return [
        SifLine(source=src, relation=rel, targets=tuple(grouped[(src, rel)]))
        for (src, rel) in order
    ]


def to_sif(edges: Sequence[dict]) -> str:
    """Собрать весь SIF-текст: строки :class:`SifLine` через ``\\n`` (§22.6).

    Пустой вход → ``""``; нет завершающей пустой строки после последней. Empty input
    yields ``""`` with no trailing blank line beyond the last.
    """
    return "\n".join(line.render() for line in group_edges(edges))
