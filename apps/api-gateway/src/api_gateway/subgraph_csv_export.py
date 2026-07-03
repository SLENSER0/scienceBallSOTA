"""CSV-сериализатор для ``GET /graph/subgraph/export?format=csv`` (§14.15).

Роутер экспорта (``routers/export.py``) умеет отдавать только JSON-LD, а
контракт §14.15 обещает ``format=json|csv`` — ветка CSV не была реализована.
Модуль на чистом stdlib (:mod:`csv`) превращает списки узлов и рёбер подграфа
в RFC 4180-совместимый CSV: каждая строка выводит именованные колонки строго по
порядку ``columns``; отсутствующий ключ даёт пустую ячейку; значения с запятой,
кавычкой или переводом строки корректно экранируются кавычками.

CSV serializer for the §14.15 ``GET /graph/subgraph/export`` endpoint: the
export router only emits JSON-LD, so the ``format=csv`` branch was unbuilt. Pure
stdlib (:mod:`csv`) — turns subgraph node/edge lists into RFC 4180 CSV. Each row
emits the named ``columns`` in order; a missing key yields an empty cell; values
containing commas, quotes or newlines are properly double-quote-escaped.

* :func:`export_nodes_csv` — узлы → CSV-текст с заголовком.
* :func:`export_edges_csv` — рёбра → CSV-текст (гарантирует ``source``/``target``).
* :class:`CsvExport` — неизменяемая пара CSV-текстов с :meth:`as_dict`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def _rows_to_csv(rows: list[Mapping[str, object]], columns: Sequence[str]) -> str:
    """Сериализовать ``rows`` в CSV по колонкам ``columns`` (RFC 4180).

    Serialize ``rows`` to CSV text using ``columns`` in order. Missing keys
    become empty cells; the header line is always emitted first. Uses
    :data:`csv.QUOTE_MINIMAL`, so only values needing it are RFC 4180-quoted.
    ``lineterminator='\\n'`` keeps a single trailing newline after the last row.
    """
    cols = list(columns)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(cols)
    for row in rows:
        writer.writerow(["" if row.get(c) is None else str(row.get(c)) for c in cols])
    return buf.getvalue()


def export_nodes_csv(nodes: list[Mapping[str, object]], columns: Sequence[str]) -> str:
    """Сериализовать узлы подграфа в CSV (§14.15).

    Serialize subgraph nodes to CSV. Header equals ``','.join(columns)``; each
    node contributes one row with the named columns in order.
    """
    return _rows_to_csv(nodes, columns)


def export_edges_csv(edges: list[Mapping[str, object]], columns: Sequence[str]) -> str:
    """Сериализовать рёбра подграфа в CSV (§14.15).

    Serialize subgraph edges to CSV, guaranteeing that ``source`` and ``target``
    appear (prepended in that order if the caller omitted them).
    """
    cols = list(columns)
    for required in ("target", "source"):
        if required not in cols:
            cols.insert(0, required)
    return _rows_to_csv(edges, cols)


@dataclass(frozen=True, slots=True)
class CsvExport:
    """Неизменяемая пара CSV-текстов узлов/рёбер подграфа (§14.15).

    Immutable pair of node/edge CSV payloads. :meth:`as_dict` yields the wire
    form ``{'nodes_csv', 'edges_csv'}`` consumed by the export endpoint.
    """

    nodes_csv: str
    edges_csv: str

    def as_dict(self) -> dict[str, str]:
        """Вернуть словарь ``{'nodes_csv','edges_csv'}`` для ответа."""
        return {"nodes_csv": self.nodes_csv, "edges_csv": self.edges_csv}
