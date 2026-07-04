"""Feature routers, attached by the API gateway app factory.

Router mounting is *resilient*: every router module is imported and included
individually, so a single broken feature router (e.g. a missing transitive
import) is skipped-and-logged instead of taking down the ENTIRE API. This kills a
recurring demo-killer where one bad import inside the monolithic
``from api_gateway.routers import (...)`` block made ``attach_routers`` raise and
the app mount *zero* routers (every path 404s).
"""

from __future__ import annotations

import importlib

from fastapi import FastAPI

try:  # structlog is the project logger; fall back to stdlib so a logging hiccup
    import structlog  # can never itself sink router mounting.

    _log = structlog.get_logger("api-gateway")
except Exception:  # pragma: no cover - defensive
    import logging

    _log = logging.getLogger("api-gateway")

# (module, router-attribute names) in MOUNT ORDER. Order matters — earlier
# routers win on any path clash:
#   * er_candidates + entity_resolve /entities/* precede search.py /entities/{id}
#   * absence GET /gaps/absence precedes gaps.py /gaps/{gap_id}
#   * er_metrics (/admin) + graph_legend (/graph) mount after admin/graph so the
#     earlier routes win.
# Do NOT reorder without re-checking those precedence constraints.
_ROUTERS: list[tuple[str, tuple[str, ...]]] = [
    ("auth", ("router",)),
    ("query", ("router",)),
    ("comparison", ("router",)),
    ("notifications", ("router",)),
    ("graph", ("router", "entities_router")),
    ("er_candidates", ("router",)),
    ("entity_resolve", ("router",)),
    ("search", ("router",)),
    ("evidence", ("router",)),
    ("admin", ("router",)),
    ("export", ("router",)),
    ("absence", ("router",)),
    ("gaps", ("router",)),
    ("curation", ("router",)),
    ("ingest", ("router",)),
    ("views", ("router",)),
    ("chat", ("router",)),
    ("experiments", ("router",)),
    ("graph_ext", ("router",)),
    ("research", ("router",)),
    ("documents", ("router",)),
    ("advise", ("router",)),
    ("contradictions", ("router",)),
    ("insights", ("router",)),
    # --- batch 1 roadmap features ---
    ("table_cell", ("router",)),
    ("mp_authority", ("router",)),
    ("voi", ("router",)),
    ("evidence_pack", ("router",)),
    ("figures", ("router",)),
    ("benchmark", ("router",)),
    ("agent_reasoning", ("router",)),
    ("agent_timeline", ("router",)),
    ("coverage_heatmap", ("router",)),
    ("community_panel", ("router",)),
    ("hardness", ("router",)),
    ("apples", ("router",)),
    ("hitl", ("router",)),
    ("chat_absence", ("router",)),
    ("link_prediction", ("router",)),
    ("missing_links", ("router",)),
    ("gap_closure", ("router",)),
    ("source_trust", ("router",)),
    ("corpus_overview", ("router",)),
    ("entity_resolution", ("router",)),
    ("gds_live", ("router",)),
    ("similarity_links", ("router",)),
    # --- batch 2 roadmap features ---
    ("graph_path", ("router",)),
    ("coverage_sankey", ("router",)),
    ("suspect_values", ("router",)),
    ("mlflow_ui", ("router",)),
    ("gliner_ner", ("router",)),
    ("similar_materials", ("router",)),
    ("similar_embeddings", ("router",)),
    ("demo_run", ("router",)),
    ("extraction_eval", ("router",)),
    ("community_cluster_graph", ("router",)),
    ("rag_checks", ("router",)),
    ("evidence_bbox", ("router",)),
    ("run_transparency", ("router",)),
    ("quality_board", ("router",)),
    ("arbiter_resolve", ("router",)),
    ("graph_encoding", ("router",)),
    ("kg_health", ("router",)),
    ("prose_claims", ("router",)),
    ("property_graph", ("router",)),
    ("unit_provenance", ("router",)),
    ("agent_trace", ("router",)),
    ("edge_anomalies", ("router",)),
    # --- batch 3 roadmap features ---
    ("batch_ingest", ("router",)),
    ("citation_provenance", ("router",)),
    ("confidence_fusion", ("router",)),
    ("er_eval", ("router",)),
    ("evidence_inspector", ("router",)),
    ("experiment_extract", ("router",)),
    ("extractor_run", ("router",)),
    ("figure_captions", ("router",)),
    ("graph_integrity", ("router",)),
    ("graph_templates", ("router",)),
    ("highlight_search", ("router",)),
    ("ingest_pipeline", ("router",)),
    ("merge_undo", ("router",)),
    ("ocr", ("router",)),
    ("ops_dashboards", ("router",)),
    ("rerank_live", ("router",)),
    ("subgraph_ask", ("router",)),
    ("table_versions", ("router",)),
    ("unit_review", ("router",)),
    ("warning_panel", ("router",)),
    # --- batch 4 roadmap features ---
    ("arbiter_evidence", ("router",)),
    ("chat_subgraph_attach", ("router",)),
    ("contradiction_scan", ("router",)),
    ("coverage_dashboard", ("router",)),
    ("curation_diff_reagraph", ("router",)),
    ("curation_graph_diff", ("router",)),
    ("definition_of_done", ("router",)),
    ("extraction_recall_eval", ("router",)),
    ("facet_search", ("router",)),
    ("fact_versions", ("router",)),
    ("golden_dataset", ("router",)),
    ("langgraph_studio", ("router",)),
    ("long_term_memory", ("router",)),
    ("new_document_sensor", ("router",)),
    ("pipeline_lineage", ("router",)),
    ("pipeline_lineage_emission", ("router",)),
    ("range_facets", ("router",)),
    ("ranking_explain", ("router",)),
    ("regression_gate", ("router",)),
    ("retrieval_eval_dashboard", ("router",)),
    ("review_task_gen", ("router",)),
    ("source_catalog", ("router",)),
    ("verifier_gate", ("router",)),
    # --- batch 5 roadmap features (final) ---
    ("collaboration", ("router",)),
    ("confidence_calibration", ("router",)),
    ("crosslingual_search", ("router",)),
    ("dagster_asset_graph", ("router",)),
    ("entity_timeline", ("router",)),
    ("er_metrics", ("router",)),
    ("expert_feedback", ("router",)),
    ("graph_legend", ("router",)),
    ("i18n", ("router",)),
    ("materials_ner", ("router",)),
    ("pipeline_dag", ("router",)),
    ("property_term_review", ("router",)),
    ("cluster_map", ("router",)),
]


def attach_routers(app: FastAPI) -> None:
    """Import + include every feature router, skipping (and logging) any that fail.

    A broken feature router (missing dependency, import error) is isolated: it is
    logged and skipped so the rest of the API still mounts. Previously one bad
    import in the batch collapsed the whole gateway to 0 routers.
    """
    mounted = 0
    skipped: list[str] = []
    for mod_name, attrs in _ROUTERS:
        try:
            mod = importlib.import_module(f"api_gateway.routers.{mod_name}")
            for attr in attrs:
                app.include_router(getattr(mod, attr))
            mounted += 1
        except Exception as exc:  # noqa: BLE001 — one bad router must not sink the app
            skipped.append(mod_name)
            _log.warning("api-gateway.router_skipped", module=mod_name, error=str(exc))
    if skipped:
        _log.warning(
            "api-gateway.routers_degraded",
            mounted=mounted,
            skipped=len(skipped),
            modules=skipped,
        )
