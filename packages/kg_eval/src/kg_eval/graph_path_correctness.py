"""Корректность путей графа — structured-retrieval graph path correctness (§18.7).

Pure-stdlib checker asserting that a structured-retrieval path (as produced by
``run_cypher_template``) traverses the required node labels in order with the
correct edge types. The canonical spine is
``Material -> ProcessingRegime -> Measurement -> Evidence`` (§15.1).

Проверяет, что путь структурного поиска проходит требуемые метки узлов в
правильном порядке и с корректными типами рёбер.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


def _is_ordered_subsequence(required: Sequence[str], observed: Sequence[str]) -> bool:
    """True, если ``required`` — упорядоченная подпоследовательность ``observed``.

    Пустой ``required`` тривиально является подпоследовательностью (True).
    """
    it = iter(observed)
    return all(any(token == want for token in it) for want in required)


@dataclass(frozen=True)
class PathCheckResult:
    """Результат проверки пути — outcome of a graph path check.

    ``ok`` is True iff node labels appear in the required order and edge types
    (when required) also appear in the required order.
    """

    node_order_ok: bool
    edge_types_ok: bool
    present_labels: tuple[str, ...]
    missing_labels: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "node_order_ok": bool(self.node_order_ok),
            "edge_types_ok": bool(self.edge_types_ok),
            "present_labels": list(self.present_labels),
            "missing_labels": list(self.missing_labels),
            "ok": bool(self.ok),
        }


def check_path(
    path_labels: Sequence[str],
    required_labels: Sequence[str],
    edge_types: Sequence[str] | None = None,
    required_edges: Sequence[str] | None = None,
) -> PathCheckResult:
    """Проверить путь графа против требуемых меток узлов и типов рёбер.

    - ``node_order_ok`` iff ``required_labels`` is an ordered subsequence of
      ``path_labels`` (extra intermediate nodes are allowed).
    - ``missing_labels`` = required labels not present anywhere in ``path_labels``.
    - ``present_labels`` = required labels that do appear in ``path_labels``.
    - ``edge_types_ok`` iff ``required_edges`` is an ordered subsequence of
      ``edge_types``; True when ``required_edges`` is None.
    - ``ok`` = ``node_order_ok and edge_types_ok``.
    """
    path_set = set(path_labels)
    present = tuple(label for label in required_labels if label in path_set)
    missing = tuple(label for label in required_labels if label not in path_set)

    node_order_ok = _is_ordered_subsequence(required_labels, path_labels)

    if required_edges is None:
        edge_types_ok = True
    else:
        edge_types_ok = _is_ordered_subsequence(required_edges, edge_types or ())

    ok = node_order_ok and edge_types_ok
    return PathCheckResult(
        node_order_ok=node_order_ok,
        edge_types_ok=edge_types_ok,
        present_labels=present,
        missing_labels=missing,
        ok=ok,
    )
