"""Graph export to Pajek ``.net`` network format — §22.

Чистый stdlib-сериализатор без доступа к графу/БД/LLM/часам: на вход — обычные
``dict`` узлов и рёбер (уже прочитанные из графа), на выход — текст Pajek ``.net``,
который импортируют VOSviewer / Gephi и инструменты сетевого анализа. Это пробел,
не закрытый существующими экспортёрами dot/gml/gexf/graphml.

Pure stdlib serializer with no graph/DB/LLM/clock access: it takes plain node and
edge ``dict``s (already read from the graph) and emits Pajek ``.net`` text that
VOSviewer / Gephi and network-analysis tools import — a gap not covered by the
existing dot/gml/gexf/graphml exporters.

Формат Pajek ``.net``:

- ``*Vertices N`` — заголовок с числом вершин;
- одна строка ``i "label"`` на вершину (1-based целочисленные id);
- ``*Arcs`` (для directed) или ``*Edges`` (для undirected);
- взвешенные строки ``i j w``.

Kuzu note: custom node props are NOT queryable columns — a retriever must RETURN
base columns and read the rest via ``get_node``; к моменту, когда ``dict`` доходит
сюда, он уже несёт нужные поля (``id`` / ``source`` / ``target``), поэтому этот
модуль не трогает store.

Entry points:

- :class:`PajekNetwork` — неизменяемая сеть ``(vertices, arcs, directed)``;
- :func:`build_network` — собрать сеть из узлов/рёбер (стабильные 1-based id);
- :func:`to_pajek` — собрать весь Pajek ``.net``-текст.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Ключ узла с идентификатором. Node id key.
_ID_KEY = "id"

# Ключи ребра для источника/цели. Edge source/target keys.
_SOURCE_KEY = "source"
_TARGET_KEY = "target"

# Вес ребра по умолчанию. Default edge weight.
_DEFAULT_WEIGHT = 1.0


@dataclass(frozen=True, slots=True)
class PajekNetwork:
    """Неизменяемая Pajek-сеть ``(vertices, arcs, directed)`` (§22).

    ``vertices`` — кортеж пар ``(id, label)`` с 1-based целочисленными id в
    порядке ввода узлов; ``arcs`` — кортеж троек ``(i, j, weight)``, где ``i``/``j``
    ссылаются на id вершин; ``directed`` выбирает заголовок ``*Arcs`` vs ``*Edges``.

    ``vertices`` holds ``(id, label)`` pairs with 1-based integer ids in node-input
    order; ``arcs`` holds ``(i, j, weight)`` triples referencing vertex ids;
    ``directed`` selects the ``*Arcs`` vs ``*Edges`` header.
    """

    vertices: tuple[tuple[int, str], ...]
    arcs: tuple[tuple[int, int, float], ...]
    directed: bool

    def as_dict(self) -> dict[str, Any]:
        """JSON-представление; кортежи → списки (list). ``directed`` round-trips."""
        return {
            "vertices": [[i, label] for (i, label) in self.vertices],
            "arcs": [[i, j, w] for (i, j, w) in self.arcs],
            "directed": self.directed,
        }


def build_network(
    nodes: list[dict],
    edges: list[dict],
    *,
    directed: bool = True,
    weight_key: str = "weight",
) -> PajekNetwork:
    """Собрать :class:`PajekNetwork` из ``nodes`` / ``edges`` (§22).

    Каждому узлу присваивается 1-based целочисленный id в стабильном порядке ввода,
    ключом служит его ``id``; метка — тоже ``str(id)``. Рёбра отображают
    ``source``/``target`` на эти id; ребро, ссылающееся на отсутствующий узел,
    пропускается (не роняет экспорт). Вес читается по ``weight_key`` (default
    ``1.0``).

    Each node gets a 1-based integer id in stable input order keyed by its ``id``;
    edges map ``source``/``target`` to those ids, default weight ``1.0``. An edge
    referencing a node id absent from ``nodes`` is dropped rather than crashing.
    """
    id_map: dict[Any, int] = {}
    vertices: list[tuple[int, str]] = []
    for node in nodes:
        node_id = node.get(_ID_KEY)
        if node_id in id_map:
            continue
        vid = len(vertices) + 1
        id_map[node_id] = vid
        vertices.append((vid, str(node_id)))

    arcs: list[tuple[int, int, float]] = []
    for edge in edges:
        src = edge.get(_SOURCE_KEY)
        dst = edge.get(_TARGET_KEY)
        if src not in id_map or dst not in id_map:
            continue
        weight = edge.get(weight_key, _DEFAULT_WEIGHT)
        arcs.append((id_map[src], id_map[dst], float(weight)))

    return PajekNetwork(
        vertices=tuple(vertices),
        arcs=tuple(arcs),
        directed=directed,
    )


def _format_weight(weight: float) -> str:
    """Формат веса: целые как ``2`` не нужны — Pajek принимает ``2.0``/``2.5``.

    Отдаёт repr float, чтобы ``1.0`` рендерился как ``1.0``, а ``2.5`` — как ``2.5``.
    """
    return repr(weight)


def to_pajek(net: PajekNetwork) -> str:
    """Собрать весь Pajek ``.net``-текст из :class:`PajekNetwork` (§22).

    Эмитит ``*Vertices N``, по строке ``i "label"`` на вершину, затем ``*Arcs``
    (directed) или ``*Edges`` (undirected) и взвешенные строки ``i j w``. Пустые
    узлы → текст начинается с ``*Vertices 0``. Строки соединяются ``\\n``.

    Emits ``*Vertices N``, one ``i "label"`` line per vertex, then ``*Arcs`` /
    ``*Edges`` with weighted ``i j w`` lines. Empty nodes → starts ``*Vertices 0``.
    """
    lines: list[str] = [f"*Vertices {len(net.vertices)}"]
    for vid, label in net.vertices:
        lines.append(f'{vid} "{label}"')
    lines.append("*Arcs" if net.directed else "*Edges")
    for i, j, weight in net.arcs:
        lines.append(f"{i} {j} {_format_weight(weight)}")
    return "\n".join(lines)
