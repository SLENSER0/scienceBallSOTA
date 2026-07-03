"""§13.11 планировщик подзадач Mode-D для графовых алгоритмов / Mode-D graph-algorithm
subtask planner (§10.1).

Modes A/B/C (lexical / vector / hybrid retrieval) are handled by ``retrieval_mode.py``.
Mode-D covers *graph-algorithm* questions — "какие материалы похожи", "чего не хватает",
"какие лаборатории важны" — that are answered by running a Graph Data Science (GDS)
algorithm rather than by retrieval. This module is a **planner only**: it maps a §10.1
Mode-D intent (a ``subtask`` key) to a concrete GDS algorithm and its parameters, and
sniffs a natural-language query for the matching subtask. Nothing here runs a server, a
GDS procedure or an LLM, so the whole module is unit-testable in isolation.

* :data:`SUBTASK_ALGO`   — subtask key → GDS algorithm name.
* :class:`GraphAlgoTask` — frozen, JSON-serialisable plan (``as_dict``).
* :func:`plan_graph_algo`  — build a validated plan for a subtask (+ ``topK`` ranking).
* :func:`detect_subtask`   — keyword-map a query to a subtask key (or ``None``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Подзадача Mode-D → имя GDS-алгоритма / Mode-D subtask → GDS algorithm name (§10.1).
SUBTASK_ALGO: dict[str, str] = {
    "similar_materials": "nodeSimilarity",
    "missing_links": "linkPrediction",
    "important_labs": "betweennessCentrality",
    "method_clusters": "louvain",
    "anomaly_detection": "anomalyDetection",
}

# Ранжирующие алгоритмы, принимающие topK / ranking algorithms that take a ``topK``.
_RANKING_ALGOS: frozenset[str] = frozenset(
    {"nodeSimilarity", "linkPrediction", "betweennessCentrality"}
)

# Ключевые слова → подзадача (порядок важен) / keyword → subtask (order matters).
_KEYWORD_SUBTASK: tuple[tuple[tuple[str, ...], str], ...] = (
    (("similar material", "materials similar", "similar to"), "similar_materials"),
    (("missing link", "predict link", "link prediction"), "missing_links"),
    (("important lab", "central lab", "key lab"), "important_labs"),
    (("cluster of method", "clusters of method", "method cluster"), "method_clusters"),
    (("anomaly", "anomalies", "outlier"), "anomaly_detection"),
)


@dataclass(frozen=True)
class GraphAlgoTask:
    """Один запланированный Mode-D подзадача → GDS-алгоритм / one planned Mode-D task.

    Frozen and JSON-serialisable via :meth:`as_dict`. ``subtask`` is the §10.1 intent
    key, ``algorithm`` the resolved GDS procedure and ``params`` its arguments (e.g.
    ``{"topK": 10}`` for ranking algorithms, ``{}`` otherwise).
    """

    subtask: str
    algorithm: str
    params: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в dict / serialise the plan to a plain ``dict``."""
        return {
            "subtask": self.subtask,
            "algorithm": self.algorithm,
            "params": dict(self.params),
        }


def plan_graph_algo(subtask: str, top_k: int = 10) -> GraphAlgoTask:
    """Построить план для Mode-D подзадачи / build a plan for a Mode-D subtask.

    Validates ``subtask`` against :data:`SUBTASK_ALGO` (raises :class:`ValueError` on an
    unknown key) and attaches ``{"topK": top_k}`` for ranking algorithms; clustering and
    anomaly algorithms get empty ``params``.
    """
    try:
        algorithm = SUBTASK_ALGO[subtask]
    except KeyError as exc:
        known = ", ".join(sorted(SUBTASK_ALGO))
        raise ValueError(
            f"неизвестная подзадача / unknown subtask: {subtask!r} (known: {known})"
        ) from exc

    params: dict[str, Any] = {"topK": top_k} if algorithm in _RANKING_ALGOS else {}
    return GraphAlgoTask(subtask=subtask, algorithm=algorithm, params=params)


def detect_subtask(query: str) -> str | None:
    """Определить Mode-D подзадачу из запроса / detect a Mode-D subtask from a query.

    Case-insensitive keyword match against :data:`_KEYWORD_SUBTASK`; returns the subtask
    key or ``None`` when the query is not a graph-algorithm question.
    """
    if not query:
        return None
    text = query.casefold()
    for keywords, subtask in _KEYWORD_SUBTASK:
        if any(kw in text for kw in keywords):
            return subtask
    return None
