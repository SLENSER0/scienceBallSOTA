"""§17.15 Unified pipeline/agent DAG for React Flow — единый DAG конвейера и агента.

RU: Экран §17.15 требует ОДИН наглядный DAG всего бэкбона платформы —
``source → parse → chunk → extract → resolve → index`` (канонический §9.1
ingestion-конвейер) **плюс** узлы LangGraph-агента ``scientific_agent`` (§7.2) — с
живыми статусами прогонов. Это «вау»-визуализация архитектуры на React Flow
(dagre/ELK layout): один граф, две дорожки (ingest + agent), мост между ними
(агент читает те самые обслуживающие хранилища, что строит конвейер), у каждого
узла — статус и метрики, у рёбер — тип (pipeline / route / retry / bridge).

Ничего не переписываем — только собираем уже готовые чистые блоки в один
React-Flow-ready payload (узлы с ``position``/``status``, рёбра с ``kind``):

* :data:`kg_common.metadata.pipeline_lineage_spec.PIPELINE_STEPS` — 12 шагов §9.1
  (in/out датасеты), из которых выводятся step→step рёбра ингеста.
* :func:`kg_common.metadata.pipeline_failure_impact.impact` — downstream-конус
  упавшего шага (для статусов ``failed`` / ``blocked`` при FAILED-прогоне).
* :func:`api_gateway.routers.pipeline_lineage._collect_runs` — реальные трассируемые
  прогоны (граф ``ExtractorRun`` на Neo4j :8000 + SQL run-registry, §10.5) —
  из них берутся живые статусы и метрики шагов ингеста.
* :func:`api_gateway.routers.langgraph_studio._canonical_topology` /
  ``_node_trace`` — канонический граф §7.2 агента и раскладка live-трассы (§18.3)
  по его узлам — для agent-дорожки и её живых статусов при ``POST /trace``.

Endpoints (prefix ``/api/v1/pipeline-dag``):

* ``GET  /graph``   — единый React-Flow DAG (ingest+agent) + live-статусы ингеста.
* ``POST /trace``   — body ``{"question": ...}`` → тот же DAG с наложенным live
  прогоном агента (статус/порядок/тайминг по узлам agent-дорожки).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_user
from api_gateway.routers.langgraph_studio import _canonical_topology, _node_trace
from api_gateway.routers.pipeline_lineage import _collect_runs
from kg_common.metadata.pipeline_failure_impact import impact
from kg_common.metadata.pipeline_lineage_spec import PIPELINE_STEPS

router = APIRouter(prefix="/api/v1/pipeline-dag", tags=["pipeline-lineage"])

# --------------------------------------------------------------------------- #
# Static wiring — human labels, lanes, bridge, layout constants.              #
# --------------------------------------------------------------------------- #

# §9.1 step → человекочитаемая подпись (RU) для узлов ingest-дорожки.
_STEP_LABEL: dict[str, str] = {
    "register_source": "Источник",
    "docling_parse": "Docling-парсинг",
    "store_parsed_s3": "S3 (parsed)",
    "chunk": "Чанкинг",
    "extract": "Извлечение триплетов",
    "normalize_units": "Нормализация единиц",
    "entity_resolution": "Разрешение сущностей",
    "validate_schema": "Валидация схемы",
    "neo4j_upsert": "Neo4j KG",
    "qdrant_index": "Qdrant индекс",
    "opensearch_index": "OpenSearch индекс",
    "gap_scan": "Скан пробелов",
}

# Обслуживающие хранилища (терминальные шаги §9.1) — это «стык» с агентом.
_STORE_STEPS: frozenset[str] = frozenset(
    {"neo4j_upsert", "qdrant_index", "opensearch_index"}
)

# Мост ingest→agent: какое хранилище какую retrieval-ветку агента «питает» (§7.2).
# Агент читает ровно те стораджи, что строит конвейер — backbone-связка для «вау».
_BRIDGE: tuple[tuple[str, str], ...] = (
    ("neo4j_upsert", "structured_retrieval"),
    ("neo4j_upsert", "graphrag_search"),
    ("neo4j_upsert", "gap_analyzer"),
    ("qdrant_index", "hybrid_retrieval"),
    ("opensearch_index", "hybrid_retrieval"),
)

# Метрики прогона → шаг, на котором их показать (узлы «со статусами/метриками»).
_STEP_METRIC_KEY: dict[str, str] = {
    "register_source": "n_documents",
    "docling_parse": "n_documents",
    "chunk": "n_chunks",
    "extract": "n_triples",
    "normalize_units": "n_triples",
    "entity_resolution": "n_triples",
}

# Layout-константы для dagre-подобной ярусной раскладки (React Flow ``position``).
_X_GAP = 240
_Y_GAP = 96
_AGENT_LANE_Y = 5 * _Y_GAP + 160  # agent-дорожка ниже ingest-дорожки


# --------------------------------------------------------------------------- #
# Ingest step→step edges (derived from §9.1 dataset in/out).                   #
# --------------------------------------------------------------------------- #
def _ingest_step_edges() -> list[tuple[str, str]]:
    """step→step рёбра ingest-дорожки: выход шага A есть вход шага B (§9.1)."""
    edges: list[tuple[str, str]] = []
    for producer in PIPELINE_STEPS:
        produced = set(producer.outputs)
        for consumer in PIPELINE_STEPS:
            if consumer.name == producer.name:
                continue
            if produced & set(consumer.inputs):
                edges.append((producer.name, consumer.name))
    return edges


# --------------------------------------------------------------------------- #
# dagre-подобная ярусная раскладка (longest-path layering).                    #
# --------------------------------------------------------------------------- #
def _forward_edges(
    nodes: list[str],
    edges: list[tuple[str, str]],
    roots: list[str],
) -> list[tuple[str, str]]:
    """Отбросить back-edges (например retry verifier→query_planner) — только вперёд.

    DFS-раскраска (white/gray/black): ребро в узел на текущем стеке рекурсии —
    back-edge и исключается, иначе длиннейший путь зацикливается. Итеративный DFS,
    чтобы не упираться в лимит рекурсии.
    """
    node_set = set(nodes)
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        if src in node_set and dst in node_set:
            adj[src].append(dst)
    color: dict[str, int] = dict.fromkeys(nodes, 0)  # 0=white 1=gray 2=black
    back: set[tuple[str, str]] = set()
    order = [r for r in roots if r in node_set] + [n for n in nodes if n not in roots]
    for start in order:
        if color[start] != 0:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        color[start] = 1
        while stack:
            node, idx = stack[-1]
            neigh = adj[node]
            if idx < len(neigh):
                stack[-1] = (node, idx + 1)
                nxt = neigh[idx]
                if color[nxt] == 1:
                    back.add((node, nxt))
                elif color[nxt] == 0:
                    color[nxt] = 1
                    stack.append((nxt, 0))
            else:
                color[node] = 2
                stack.pop()
    return [(s, t) for s, t in edges if (s, t) not in back and s in node_set and t in node_set]


def _layer_map(
    nodes: list[str],
    edges: list[tuple[str, str]],
    roots: list[str],
) -> dict[str, int]:
    """Ярус каждого узла = длиннейший путь от корня (back-edges отброшены).

    Итеративная релаксация ``layer[t] = max(layer[t], layer[s] + 1)`` по forward-
    рёбрам за ``len(nodes)`` проходов — детерминированно для DAG без циклов.
    """
    layer: dict[str, int] = dict.fromkeys(nodes, 0)
    forward = _forward_edges(nodes, edges, roots)
    for _ in range(max(1, len(nodes))):
        changed = False
        for src, dst in forward:
            want = layer[src] + 1
            if want > layer[dst]:
                layer[dst] = want
                changed = True
        if not changed:
            break
    for r in roots:
        if r in layer:
            layer[r] = 0
    return layer


def _positions(
    nodes: list[str],
    layer: dict[str, int],
    y_base: int,
) -> dict[str, dict[str, int]]:
    """Позиции ``{x, y}`` по ярусам: x = слой·gap, y = смещение внутри яруса."""
    by_layer: dict[int, list[str]] = {}
    for n in nodes:
        by_layer.setdefault(layer.get(n, 0), []).append(n)
    pos: dict[str, dict[str, int]] = {}
    for lyr, members in by_layer.items():
        for idx, n in enumerate(members):
            pos[n] = {"x": lyr * _X_GAP, "y": y_base + idx * _Y_GAP}
    return pos


# --------------------------------------------------------------------------- #
# Live ingest statuses/metrics from real §10.5 runs.                           #
# --------------------------------------------------------------------------- #
def _ingest_statuses() -> tuple[dict[str, str], dict[str, Any] | None]:
    """Живые статусы шагов ингеста из последнего трассируемого прогона (§10.5).

    SUCCESS-прогон → все шаги ``success``; FAILED → упавший шаг ``failed``, его
    downstream-конус (``impact``) ``blocked``, остальные ``success``; RUNNING →
    ``running``; прогонов нет → всё ``idle``. Возвращает ещё сам последний прогон
    (для метрик на узлах).
    """
    statuses = {step.name: "idle" for step in PIPELINE_STEPS}
    try:
        runs = _collect_runs()
    except Exception:  # pragma: no cover - live store may be unavailable
        return statuses, None
    if not runs:
        return statuses, None
    latest = runs[0]
    status = str(latest.get("status", "")).upper()
    if status == "FAILED":
        failed = str(latest.get("failed_step") or "extract")
        try:
            blocked = set(impact(failed).blocked_steps)
        except ValueError:
            failed, blocked = "extract", set(impact("extract").blocked_steps)
        for step in PIPELINE_STEPS:
            if step.name == failed:
                statuses[step.name] = "failed"
            elif step.name in blocked:
                statuses[step.name] = "blocked"
            else:
                statuses[step.name] = "success"
    elif status == "RUNNING":
        statuses = {step.name: "running" for step in PIPELINE_STEPS}
    else:  # SUCCESS (graph-derived runs are, by construction, successful)
        statuses = {step.name: "success" for step in PIPELINE_STEPS}
    return statuses, latest


def _step_metric(step_name: str, latest: dict[str, Any] | None) -> dict[str, Any]:
    """Метрика узла ingest из последнего прогона (документы/чанки/триплеты)."""
    if latest is None:
        return {}
    key = _STEP_METRIC_KEY.get(step_name)
    if key is None:
        return {}
    value = latest.get(key)
    if not value:
        return {}
    return {"metricKey": key, "metricValue": int(value)}


# --------------------------------------------------------------------------- #
# Build the unified DAG (ingest lane + agent lane + bridge).                   #
# --------------------------------------------------------------------------- #
def _build_ingest(
    statuses: dict[str, str], latest: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Ingest-дорожка: узлы (со статусами/метриками) + step→step рёбра (§9.1)."""
    step_names = [s.name for s in PIPELINE_STEPS]
    edges = _ingest_step_edges()
    layer = _layer_map(step_names, edges, roots=["register_source"])
    pos = _positions(step_names, layer, y_base=0)

    nodes: list[dict[str, Any]] = []
    for step in PIPELINE_STEPS:
        is_store = step.name in _STORE_STEPS
        nodes.append(
            {
                "id": f"ingest:{step.name}",
                "section": "ingest",
                "kind": "store" if is_store else "step",
                "label": _STEP_LABEL.get(step.name, step.name),
                "ref": step.name,
                "status": statuses.get(step.name, "idle"),
                "layer": layer.get(step.name, 0),
                "position": pos[step.name],
                "isStore": is_store,
                **_step_metric(step.name, latest),
            }
        )

    edge_dicts = [
        {
            "id": f"ie:{src}->{dst}",
            "source": f"ingest:{src}",
            "target": f"ingest:{dst}",
            "kind": "pipeline",
        }
        for src, dst in edges
    ]
    return nodes, edge_dicts


def _build_agent(
    canonical: dict[str, Any], overlay: dict[str, str] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Agent-дорожка: канонический §7.2 граф scientific_agent + опц. live-статусы."""
    agent_nodes = canonical["nodes"]
    agent_edges = [(e["source"], e["target"]) for e in canonical["edges"]]
    ids = [n["id"] for n in agent_nodes]
    layer = _layer_map(ids, agent_edges, roots=["START"])
    pos = _positions(ids, layer, y_base=_AGENT_LANE_Y)

    nodes: list[dict[str, Any]] = []
    for n in agent_nodes:
        nid = n["id"]
        term = n.get("isStart") or n.get("isEnd")
        if term:
            node_kind = "terminal"
        elif n.get("isRetrievalBranch"):
            node_kind = "branch"
        else:
            node_kind = "node"
        nodes.append(
            {
                "id": f"agent:{nid}",
                "section": "agent",
                "kind": node_kind,
                "label": n.get("label", nid),
                "ref": nid,
                "status": (overlay or {}).get(nid, "idle"),
                "layer": layer.get(nid, 0),
                "position": pos[nid],
                "isRetrievalBranch": bool(n.get("isRetrievalBranch")),
                "rationale": n.get("rationale", ""),
            }
        )

    edge_dicts: list[dict[str, Any]] = []
    for src, dst in agent_edges:
        if src == "query_planner" and dst in {
            "structured_retrieval",
            "hybrid_retrieval",
            "graphrag_search",
            "gap_analyzer",
        }:
            kind = "route"
        elif src == "verifier" and dst == "query_planner":
            kind = "retry"
        else:
            kind = "pipeline"
        edge_dicts.append(
            {
                "id": f"ae:{src}->{dst}",
                "source": f"agent:{src}",
                "target": f"agent:{dst}",
                "kind": kind,
            }
        )
    return nodes, edge_dicts


def _bridge_edges() -> list[dict[str, Any]]:
    """Мост ingest→agent: обслуживающие хранилища «питают» retrieval-ветки агента."""
    return [
        {
            "id": f"be:{store}->{branch}",
            "source": f"ingest:{store}",
            "target": f"agent:{branch}",
            "kind": "bridge",
        }
        for store, branch in _BRIDGE
    ]


def _assemble(overlay: dict[str, str] | None = None) -> dict[str, Any]:
    """Собрать единый React-Flow DAG: ingest-дорожка + agent-дорожка + мост."""
    statuses, latest = _ingest_statuses()
    ingest_nodes, ingest_edges = _build_ingest(statuses, latest)
    canonical = _canonical_topology()
    agent_nodes, agent_edges = _build_agent(canonical, overlay)

    nodes = ingest_nodes + agent_nodes
    edges = ingest_edges + agent_edges + _bridge_edges()

    latest_run = None
    if latest is not None:
        latest_run = {
            "job_id": latest.get("job_id", ""),
            "status": str(latest.get("status", "")).upper(),
            "n_documents": int(latest.get("n_documents", 0) or 0),
            "n_chunks": int(latest.get("n_chunks", 0) or 0),
            "n_triples": int(latest.get("n_triples", 0) or 0),
            "created_at": latest.get("created_at", ""),
        }

    return {
        "graphId": "pipeline_agent_backbone",
        "lanes": [
            {"id": "ingest", "label": "Ingestion §9.1", "y": 0},
            {"id": "agent", "label": "LangGraph агент §7.2", "y": _AGENT_LANE_Y},
        ],
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "ingestNodes": len(ingest_nodes),
            "agentNodes": len(agent_nodes),
            "bridges": len(_BRIDGE),
        },
        "latestRun": latest_run,
    }


# --------------------------------------------------------------------------- #
# GET /graph — статичный backbone-DAG + live-статусы ингеста.                  #
# --------------------------------------------------------------------------- #
@router.get("/graph")
def dag_graph(user: str = Depends(current_user)) -> dict:
    """Единый pipeline/agent DAG для React Flow (§17.15).

    Ingest-дорожка §9.1 (source→parse→…→index) с живыми статусами и метриками
    последнего трассируемого прогона (§10.5), agent-дорожка §7.2 (scientific_agent,
    узлы idle до прогона трассы) и мост между ними (агент читает обслуживающие
    хранилища, что строит конвейер). Узлы несут ``position`` (dagre-подобная ярусная
    раскладка) и ``status``; рёбра — ``kind`` (pipeline/route/retry/bridge).
    """
    return _assemble(overlay=None)


# --------------------------------------------------------------------------- #
# POST /trace — тот же DAG + live прогон агента, наложенный на его узлы.        #
# --------------------------------------------------------------------------- #
class TraceBody(BaseModel):
    """POST /trace payload — вопрос пользователя / the user's question."""

    question: str


def _agent_overlay(question: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Живой прогон §18.3-трассы, разложенный по узлам agent-дорожки (§7.2).

    Переиспользует ``agent_trace._run_tree`` (живые Cypher-чтения по графу) и
    ``langgraph_studio._node_trace`` (раскладка трассы по каноническим узлам).
    Возвращает карту ``node→status`` для наложения на DAG и сырую сводку трассы.
    """
    from api_gateway.deps import get_store
    from api_gateway.routers.agent_trace import _run_tree

    store = get_store()
    run = _run_tree(store, question)
    canonical = _canonical_topology()
    node_trace = _node_trace(canonical, run)

    overlay: dict[str, str] = {}
    for row in node_trace.get("overlay", []):
        overlay[row["node"]] = str(row.get("status", "idle"))
    # START/END подсвечиваем как исполненные, раз трасса прошла.
    overlay.setdefault("START", "ok")
    overlay["END"] = "ok"

    summary = {
        "traceId": run.get("traceId"),
        "intent": run.get("intent"),
        "totalDurationMs": run.get("totalDurationMs"),
        "spanCount": run.get("spanCount"),
        "statusCounts": run.get("statusCounts"),
        "executedPath": node_trace.get("executedPath", []),
        "executedNodes": node_trace.get("executedNodes", []),
        "executedCount": node_trace.get("executedCount", 0),
        "nodeOverlay": node_trace.get("overlay", []),
    }
    return overlay, summary


@router.post("/trace")
def dag_trace(body: TraceBody, user: str = Depends(current_user)) -> dict:
    """Единый DAG + наложенный live-прогон агента по конкретному вопросу (§17.15).

    Реально прогоняет §18.3-трассу и раскладывает её по узлам agent-дорожки: у
    исполненных узлов статус/порядок из трассы, у прочих — ``idle``/``skipped``.
    Ingest-дорожка остаётся с живыми статусами последнего прогона. Возвращает тот
    же React-Flow payload плюс сводку трассы (``trace``).
    """
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    overlay, summary = _agent_overlay(question)
    dag = _assemble(overlay=overlay)
    dag["question"] = question
    dag["trace"] = summary
    return dag
