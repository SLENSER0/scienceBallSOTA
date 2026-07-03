"""PathRAG flow-pruned relational-path retrieval (§12.2 / §12.5).

Реализация PathRAG — извлечение реляционных путей между двумя узлами KG с
"потоковым" прунингом (flow-based pruning): из источника пускается ресурс,
затухающий на каждом переходе, и оставляются пути с наибольшим доходящим потоком.

Paper / источник:
    PathRAG: Pruning Graph-based Retrieval Augmented Generation with Relational
    Paths. Boyu Chen et al. (BUPT-GAMMA / MIT). arXiv:2502.14902.
    https://arxiv.org/abs/2502.14902 — https://github.com/BUPT-GAMMA/PathRAG

Pipeline / конвейер:
- :func:`find_paths` — перечисляет простые пути ``src -> dst`` длиной до
  ``max_hops`` рёбер, оценивает надёжность (reliability) каждого как
  ``decay ** hops * ∏ edge_weight``, оставляет ``top_n`` лучших (flow-pruning),
  остальные складывает в ``pruned``;
- :func:`linearize` — превращает путь в текстовую строку для промпта LLM,
  вида ``a -[REL]-> b -[REL2]-> c``.

Каждый вес ребра берётся из ``r.confidence`` (или ``weight_default`` при
``NULL``). Обход направленный и читает только базовые Kuzu-колонки
(``a.id, r.type, b.id, r.confidence``) — кастомные props не являются
запрашиваемыми колонками (§3 / ADR-0005), но здесь и не нужны.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Edge in adjacency form: (target_id, rel_type, confidence-or-None).
_Adj = dict[str, list[tuple[str, str, float | None]]]
# Traversal edge: (source_id, rel_type, target_id, confidence-or-None).
_Edge = tuple[str, str, str, float | None]

DEFAULT_WEIGHT = 0.8  # надёжность ребра по умолчанию, когда confidence отсутствует
DEFAULT_DECAY = 0.8  # затухание потока на каждый переход (per-hop decay)


@dataclass(frozen=True)
class PathResult:
    """Результат PathRAG: оставленные пути + отсечённые прунингом (§12.5).

    ``paths`` / ``pruned`` — кортежи path-словарей ``{nodes, edges, reliability}``,
    отсортированные по убыванию reliability (потока). ``paths`` — топ-``top_n``,
    ``pruned`` — всё, что не прошло flow-based pruning.
    """

    paths: tuple[dict[str, Any], ...]
    pruned: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Serialise to ``{"paths": [...], "pruned": [...]}`` (deep-copies paths)."""
        return {
            "paths": [_copy_path(p) for p in self.paths],
            "pruned": [_copy_path(p) for p in self.pruned],
        }


def _copy_path(path: dict[str, Any]) -> dict[str, Any]:
    """Copy a path dict so callers cannot mutate the frozen result in place."""
    return {
        "nodes": list(path["nodes"]),
        "edges": [dict(e) for e in path["edges"]],
        "reliability": path["reliability"],
    }


def _edge_weight(confidence: float | None, weight_default: float) -> float:
    """Вес ребра: confidence, либо ``weight_default`` при ``NULL``."""
    return weight_default if confidence is None else float(confidence)


def _adjacency(store: KuzuGraphStore) -> _Adj:
    """Directed adjacency from base Kuzu columns; neighbours sorted for determinism."""
    rows = store.rows("MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, r.type, b.id, r.confidence")
    adj: _Adj = {}
    for src, rel_type, dst, confidence in rows:
        adj.setdefault(src, []).append((dst, rel_type, confidence))
    for nbrs in adj.values():
        nbrs.sort(key=lambda e: (e[0], e[1]))
    return adj


def _enumerate_paths(adj: _Adj, src: str, dst: str, max_hops: int) -> list[list[_Edge]]:
    """Все простые пути ``src -> dst`` длиной до ``max_hops`` рёбер (DFS, без циклов)."""
    out: list[list[_Edge]] = []
    if max_hops < 1 or src == dst:
        return out
    visited: set[str] = {src}
    edges: list[_Edge] = []

    def dfs(node: str) -> None:
        for nxt, rel_type, confidence in adj.get(node, []):
            if nxt in visited:
                continue
            edges.append((node, rel_type, nxt, confidence))
            if nxt == dst:
                out.append(list(edges))  # terminal: record, do not extend past dst
            elif len(edges) < max_hops:
                visited.add(nxt)
                dfs(nxt)
                visited.discard(nxt)
            edges.pop()

    dfs(src)
    return out


def _reliability(edges: list[_Edge], decay: float, weight_default: float) -> float:
    """Потоковая надёжность пути: ``decay ** hops * ∏ edge_weight`` (§12.5)."""
    score = decay ** len(edges)
    for _, _, _, confidence in edges:
        score *= _edge_weight(confidence, weight_default)
    return score


def _path_dict(edges: list[_Edge], decay: float, weight_default: float) -> dict[str, Any]:
    """Build the public ``{nodes, edges, reliability}`` path representation."""
    nodes = [edges[0][0]] + [dst for _, _, dst, _ in edges]
    edge_dicts = [
        {"source": s, "type": t, "target": d, "weight": _edge_weight(c, weight_default)}
        for s, t, d, c in edges
    ]
    return {
        "nodes": nodes,
        "edges": edge_dicts,
        "reliability": _reliability(edges, decay, weight_default),
    }


def find_paths(
    store: KuzuGraphStore,
    src: str,
    dst: str,
    *,
    max_hops: int = 4,
    top_n: int = 5,
    decay: float = DEFAULT_DECAY,
    weight_default: float = DEFAULT_WEIGHT,
) -> PathResult:
    """Извлечь реляционные пути ``src -> dst`` с потоковым прунингом (PathRAG, §12.5).

    Перечисляет простые пути длиной до ``max_hops`` рёбер, оценивает каждый по
    надёжности ``decay ** hops * ∏ edge_weight`` (вес = ``r.confidence`` или
    ``weight_default``), сортирует по убыванию надёжности и оставляет ``top_n``
    лучших в ``paths``; остальные (отсечённые) — в ``pruned``. Если путей нет,
    оба кортежа пусты.
    """
    adj = _adjacency(store)
    scored = [
        _path_dict(e, decay, weight_default) for e in _enumerate_paths(adj, src, dst, max_hops)
    ]
    scored.sort(key=lambda p: (-p["reliability"], len(p["nodes"]), tuple(p["nodes"])))
    keep = max(0, top_n)
    return PathResult(paths=tuple(scored[:keep]), pruned=tuple(scored[keep:]))


def linearize(path: dict[str, Any]) -> str:
    """Текстовое представление пути для промпта LLM: ``a -[REL]-> b -[REL2]-> c``."""
    edges = path.get("edges", [])
    if not edges:
        return ""
    parts: list[str] = [str(edges[0]["source"])]
    for edge in edges:
        parts.append(f"-[{edge['type']}]->")
        parts.append(str(edge["target"]))
    return " ".join(parts)
