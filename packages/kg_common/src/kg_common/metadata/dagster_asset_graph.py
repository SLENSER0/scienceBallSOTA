"""Canonical §9.2 Dagster asset graph — полный asset-граф ingestion/indexing (§9.2).

Dagit (the Dagster web UI on port 3001) is an *optional* container: in the live
server-profile it is frequently not running, yet §9.2 still requires the full
software-defined asset graph to be **projectable into UI/JSON** («Проекция ассетов
в UI/JSON, если Dagit недоступен») and the seed document to be materializable
end-to-end from ``source_registration`` to ``retrieval_eval``.

This module pins down that graph as pure, Dagster-free data so it can be served
without importing ``dagster`` or reaching Dagit:

* :class:`AssetSpec`   — one software-defined asset («ассет») exactly as declared in
  §9.2: ``key``, its Dagit ``group_name``/layer, the §9.1 pipeline ``step`` it
  implements, the upstream asset ``deps``, and the graph-store ``evidence_labels``
  whose live node counts prove the asset actually produced something.
* :data:`ASSETS`       — the fourteen canonical §9.2 assets (≥12 as the acceptance
  criterion demands), in DAG order.
* :data:`ASSET_JOBS`   — the ``define_asset_job`` subsets from §9.2
  (``full_ingestion_job``, ``parse_only_job``, ``extract_only_job``,
  ``reindex_job``, ``community_summary_job``, ``gap_scan_job``).
* :func:`build_graph`  — assemble a :class:`kg_common.asset_graph.AssetGraph` so the
  deterministic topological order / layer grouping is reused, not re-implemented.
* :func:`graph_projection` — the JSON payload a router/Dagit-fallback UI renders.

Everything here is deterministic and side-effect free; the *live* materialization
evidence (node counts per asset) is layered on top by the API router, which owns the
graph store.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from kg_common.asset_graph import AssetGraph

__all__ = [
    "ASSETS",
    "ASSET_INDEX",
    "ASSET_JOBS",
    "LAYERS",
    "AssetSpec",
    "build_graph",
    "graph_projection",
    "job_asset_keys",
    "layers",
    "topo_order",
]


# The ordered Dagit group/layer names (asset-key prefixes) from §9.2 — истоки слева,
# analytics-хвост справа. Used to bucket assets into pipeline layers for the UI.
LAYERS: tuple[str, ...] = ("raw", "parse", "extract", "graph", "index", "analytics")


@dataclass(frozen=True, slots=True)
class AssetSpec:
    """One §9.2 software-defined asset — один Dagster-ассет (§9.2).

    ``key`` is the asset key; ``group_name`` is the Dagit group/layer (one of
    :data:`LAYERS`); ``step`` is the §9.1 pipeline step it implements; ``deps`` are
    the upstream asset keys (edges of the asset graph); ``kind`` is
    ``per_document`` (materialized once per ``doc_id`` partition) or ``corpus``
    (aggregating over the whole graph). ``evidence_labels`` are the graph-store node
    labels whose live counts show the asset produced real output; ``serving`` names
    an *external* store (Qdrant/OpenSearch/S3/Dagit) that this projection cannot
    query directly, so its counters are honestly reported as *projected*.
    """

    key: str
    group_name: str
    step: str
    kind: str
    title: str
    description: str
    deps: tuple[str, ...] = ()
    evidence_labels: tuple[str, ...] = ()
    serving: str | None = None
    aggregate: str | None = None  # "graph_totals" | "communities" | None

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view of the asset declaration — ассет как словарь (§9.2)."""
        return {
            "key": self.key,
            "group_name": self.group_name,
            "step": self.step,
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
            "deps": list(self.deps),
            "evidence_labels": list(self.evidence_labels),
            "serving": self.serving,
            "aggregate": self.aggregate,
        }


# Fourteen canonical §9.2 assets in DAG order. Deps follow the mermaid graph of
# §9.1 exactly (see §9.2: graph_upsert и *_indexing зависят от schema_validation;
# gap_scan/community_summarization от graph_upsert; retrieval_eval от обоих
# indexing-ассетов; индексация community-summaries в qdrant_indexing — от
# community_summarization).
ASSETS: tuple[AssetSpec, ...] = (
    AssetSpec(
        key="source_registration",
        group_name="raw",
        step="Step 1 · REGISTER",
        kind="per_document",
        title="Регистрация источника",
        description=(
            "Регистрирует source в Postgres (source id, file hash, source type, "
            "owner/lab, access policy, ingestion job id, version) и эмитит "
            "регистрацию в каталог DataHub/OpenMetadata."
        ),
        deps=(),
        evidence_labels=("Document", "Paper", "Source"),
    ),
    AssetSpec(
        key="docling_parse",
        group_name="parse",
        step="Step 2 · PARSE",
        kind="per_document",
        title="Docling-парсинг",
        description=(
            "Вызывает Docling Serve (порт 5001): markdown, structured JSON, tables, "
            "document hierarchy, page references."
        ),
        deps=("source_registration",),
        evidence_labels=("Document", "Paper"),
    ),
    AssetSpec(
        key="store_parsed_artifacts",
        group_name="parse",
        step="Step 2 · STORE",
        kind="per_document",
        title="Артефакты парсинга в S3/MinIO",
        description=(
            "Пишет original.pdf / docling.json / document.md / tables/table_*.json в "
            "s3://kg-raw и s3://kg-parsed по путям §9.2 Step 2."
        ),
        deps=("docling_parse",),
        evidence_labels=("Document", "Paper"),
        serving="s3",
    ),
    AssetSpec(
        key="chunking",
        group_name="parse",
        step="Step 3 · CHUNK",
        kind="per_document",
        title="Structure-aware чанкинг",
        description=(
            "Structure-aware чанки (title/abstract, methods, results, captions, "
            "table rows, procedure paragraphs) со схемой chunk из §9.2 Step 3."
        ),
        deps=("store_parsed_artifacts",),
        evidence_labels=("Chunk",),
    ),
    AssetSpec(
        key="extraction",
        group_name="extract",
        step="Step 4 · EXTRACT",
        kind="per_document",
        title="Извлечение фактов",
        description=(
            "Rule/domain-экстракторы + GLiNER NER + LLM schema-guided extraction по "
            "Pydantic-схемам; каждый факт требует evidence span."
        ),
        deps=("chunking",),
        evidence_labels=(
            "Measurement",
            "Finding",
            "Contradiction",
            "Composition",
            "Parameter",
            "Evidence",
        ),
    ),
    AssetSpec(
        key="units_normalization",
        group_name="extract",
        step="Step 5 · NORMALIZE",
        kind="per_document",
        title="Нормализация единиц и материалов",
        description=(
            "pint + маппинги HV/HRC/MPa/GPa (value_raw/value_normalized/"
            "normalized_unit) и canonical naming материалов."
        ),
        deps=("extraction",),
        evidence_labels=("Measurement", "Parameter"),
    ),
    AssetSpec(
        key="entity_resolution",
        group_name="extract",
        step="Step 6 · RESOLVE",
        kind="per_document",
        title="Разрешение сущностей (Splink)",
        description=(
            "Splink jobs для Material/Equipment/Person/Lab/Property: candidate_id / "
            "mentions / match_probability / decision."
        ),
        deps=("units_normalization",),
        evidence_labels=(
            "Material",
            "Equipment",
            "Person",
            "Lab",
            "ChemicalElement",
            "Property",
            "Composition",
            "Facility",
            "Country",
            "Geography",
        ),
    ),
    AssetSpec(
        key="schema_validation",
        group_name="extract",
        step="VALIDATE",
        kind="per_document",
        title="Валидация схемы (Pydantic/LinkML)",
        description=(
            "Валидация Pydantic/LinkML; невалидные факты уходят в отдельный "
            "output/review."
        ),
        deps=("entity_resolution",),
        evidence_labels=("Measurement", "Evidence", "Material", "Property"),
    ),
    AssetSpec(
        key="graph_upsert",
        group_name="graph",
        step="Step 7 · UPSERT",
        kind="per_document",
        title="Upsert в Neo4j",
        description=(
            "MERGE по каноническим id (deterministic IDs, never overwrite reviewed "
            "fields, store extraction run id, preserve previous versions)."
        ),
        deps=("schema_validation",),
        aggregate="graph_totals",
    ),
    AssetSpec(
        key="community_summarization",
        group_name="analytics",
        step="§10.3 · COMMUNITY",
        kind="corpus",
        title="Суммаризация сообществ",
        description=(
            "Community detection (Louvain/Leiden) над графом + LLM-генерация "
            "neighborhood- и community-summaries; корпус-уровневый ассет."
        ),
        deps=("graph_upsert",),
        aggregate="communities",
    ),
    AssetSpec(
        key="qdrant_indexing",
        group_name="index",
        step="Step 8 · INDEX (vectors)",
        kind="per_document",
        title="Индексация в Qdrant",
        description=(
            "Индексирует chunks/table rows/claims/entity descriptions/community "
            "summaries с payload §9.2 Step 8; summaries — от community_summarization."
        ),
        deps=("schema_validation", "community_summarization"),
        evidence_labels=("Chunk",),
        serving="qdrant",
    ),
    AssetSpec(
        key="opensearch_indexing",
        group_name="index",
        step="Step 8 · INDEX (BM25)",
        kind="per_document",
        title="Индексация в OpenSearch",
        description="Full text / keywords / facets / numeric ranges / highlight fields.",
        deps=("schema_validation",),
        evidence_labels=("Chunk",),
        serving="opensearch",
    ),
    AssetSpec(
        key="gap_scan",
        group_name="analytics",
        step="GAP · §11",
        kind="corpus",
        title="Скан пробелов",
        description=(
            "Gap-scan Cypher (missing_baseline, material/regime/property matrix "
            "gaps) после graph_upsert."
        ),
        deps=("graph_upsert",),
        evidence_labels=("Gap", "GapScanRun"),
    ),
    AssetSpec(
        key="retrieval_eval",
        group_name="analytics",
        step="EVAL · §15",
        kind="corpus",
        title="Оценка ретривала",
        description="Прогоняет retrieval eval после индексации (§15).",
        deps=("qdrant_indexing", "opensearch_indexing"),
        serving="eval",
    ),
)


ASSET_INDEX: dict[str, AssetSpec] = {a.key: a for a in ASSETS}


# ``define_asset_job`` subsets from §9.2. Each names an explicit selection of asset
# keys (the router expands upstream deps when it wants the runnable closure).
ASSET_JOBS: dict[str, tuple[str, ...]] = {
    "full_ingestion_job": tuple(a.key for a in ASSETS),
    "parse_only_job": (
        "source_registration",
        "docling_parse",
        "store_parsed_artifacts",
        "chunking",
    ),
    "extract_only_job": (
        "extraction",
        "units_normalization",
        "entity_resolution",
        "schema_validation",
    ),
    "reindex_job": ("qdrant_indexing", "opensearch_indexing"),
    "community_summary_job": ("community_summarization", "qdrant_indexing"),
    "gap_scan_job": ("gap_scan",),
}


def build_graph() -> AssetGraph:
    """Assemble the §9.2 asset graph — сборка графа ассетов (§9.2).

    Reuses :class:`kg_common.asset_graph.AssetGraph` so the topological order,
    roots/leaves and up/downstream closures are the shared, deterministic
    implementation rather than a re-write.
    """
    graph = AssetGraph()
    for asset in ASSETS:
        graph.add_asset(asset.key, asset.deps)
    return graph


def topo_order() -> list[str]:
    """Deterministic build order over the §9.2 assets — топопорядок (§9.2)."""
    return build_graph().topo_order()


def layers() -> list[dict[str, object]]:
    """Group assets by their Dagit layer — раскладка по слоям (§9.2).

    Layers are returned in the canonical :data:`LAYERS` order so the UI renders
    ``raw → parse → extract → graph → index → analytics`` left-to-right.
    """
    buckets: dict[str, list[str]] = {layer: [] for layer in LAYERS}
    for asset in ASSETS:
        buckets.setdefault(asset.group_name, []).append(asset.key)
    return [
        {"group": layer, "assets": buckets[layer]}
        for layer in LAYERS
        if buckets.get(layer)
    ]


def job_asset_keys(job: str, *, closure: bool = False) -> list[str]:
    """Return a job's asset keys in topo order — ассеты джоба (§9.2).

    With ``closure=True`` the transitive upstream assets required to run the
    selection are folded in (what Dagster would actually schedule).
    """
    selection = set(ASSET_JOBS.get(job, ()))
    if not selection:
        return []
    if closure:
        graph = build_graph()
        expanded = set(selection)
        for key in selection:
            expanded.update(graph.upstream_of(key))
        selection = expanded
    order = topo_order()
    return [k for k in order if k in selection]


def graph_projection() -> dict[str, object]:
    """Full JSON projection of the §9.2 asset graph — проекция для UI/JSON (§9.2).

    This is the Dagit-independent view: assets, dependency edges, deterministic
    topological order, layer buckets, the roots/leaves and every ``define_asset_job``
    subset. The live materialization evidence is overlaid by the API router.
    """
    graph = build_graph()
    order = topo_order()
    edges = [
        {"source": dep, "target": asset.key}
        for asset in ASSETS
        for dep in asset.deps
    ]
    jobs = [
        {
            "name": name,
            "selection": list(keys),
            "assets": job_asset_keys(name),
            "run_closure": job_asset_keys(name, closure=True),
        }
        for name, keys in ASSET_JOBS.items()
    ]
    return {
        "assets": [a.as_dict() for a in ASSETS],
        "edges": edges,
        "topo_order": order,
        "layers": layers(),
        "roots": graph.roots(),
        "leaves": graph.leaves(),
        "jobs": jobs,
        "asset_count": len(ASSETS),
        "layer_order": list(LAYERS),
    }


def missing_assets(emitted: Sequence[str]) -> tuple[str, ...]:
    """Canonical §9.2 asset keys absent from ``emitted`` — пропущенные ассеты (§9.2)."""
    seen = set(emitted)
    return tuple(a.key for a in ASSETS if a.key not in seen)
