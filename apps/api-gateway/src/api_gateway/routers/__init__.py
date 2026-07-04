"""Feature routers, attached by the API gateway app factory."""

from __future__ import annotations

from fastapi import FastAPI


def attach_routers(app: FastAPI) -> None:
    from api_gateway.routers import (
        absence,
        admin,
        advise,
        agent_reasoning,
        agent_timeline,
        # batch 2
        agent_trace,
        apples,
        arbiter_resolve,
        auth,
        benchmark,
        chat,
        chat_absence,
        community_cluster_graph,
        community_panel,
        comparison,
        contradictions,
        corpus_overview,
        coverage_heatmap,
        coverage_sankey,
        curation,
        demo_run,
        documents,
        edge_anomalies,
        entity_resolution,
        er_candidates,
        evidence,
        evidence_bbox,
        evidence_pack,
        experiments,
        export,
        extraction_eval,
        figures,
        gap_closure,
        gaps,
        gds_live,
        gliner_ner,
        graph,
        graph_encoding,
        graph_ext,
        graph_path,
        hardness,
        hitl,
        ingest,
        insights,
        kg_health,
        link_prediction,
        missing_links,
        mlflow_ui,
        mp_authority,
        notifications,
        property_graph,
        prose_claims,
        quality_board,
        query,
        rag_checks,
        research,
        run_transparency,
        search,
        similar_embeddings,
        similar_materials,
        similarity_links,
        source_trust,
        suspect_values,
        table_cell,
        unit_provenance,
        views,
        voi,
    )

    app.include_router(auth.router)
    app.include_router(query.router)
    app.include_router(comparison.router)
    app.include_router(notifications.router)
    app.include_router(graph.router)
    app.include_router(graph.entities_router)
    # er_candidates GET /entities/candidates must precede search.py's /entities/{entity_id}
    app.include_router(er_candidates.router)
    app.include_router(search.router)
    app.include_router(evidence.router)
    app.include_router(admin.router)
    app.include_router(export.router)
    # absence GET /gaps/absence must precede gaps.py's /gaps/{gap_id}
    app.include_router(absence.router)
    app.include_router(gaps.router)
    app.include_router(curation.router)
    app.include_router(ingest.router)
    app.include_router(views.router)
    app.include_router(chat.router)
    app.include_router(experiments.router)
    app.include_router(graph_ext.router)
    app.include_router(research.router)
    app.include_router(documents.router)
    app.include_router(advise.router)
    app.include_router(contradictions.router)
    app.include_router(insights.router)
    # --- batch 1 roadmap features (er_candidates already mounted above) ---
    app.include_router(table_cell.router)
    app.include_router(mp_authority.router)
    app.include_router(voi.router)
    app.include_router(evidence_pack.router)
    app.include_router(figures.router)
    app.include_router(benchmark.router)
    app.include_router(agent_reasoning.router)
    app.include_router(agent_timeline.router)
    app.include_router(coverage_heatmap.router)
    app.include_router(community_panel.router)
    app.include_router(hardness.router)
    app.include_router(apples.router)
    app.include_router(hitl.router)
    app.include_router(chat_absence.router)
    app.include_router(link_prediction.router)
    app.include_router(missing_links.router)
    app.include_router(gap_closure.router)
    app.include_router(source_trust.router)
    app.include_router(corpus_overview.router)
    app.include_router(entity_resolution.router)
    app.include_router(gds_live.router)
    app.include_router(similarity_links.router)
    # --- batch 2 roadmap features ---
    app.include_router(graph_path.router)
    app.include_router(coverage_sankey.router)
    app.include_router(suspect_values.router)
    app.include_router(mlflow_ui.router)
    app.include_router(gliner_ner.router)
    app.include_router(similar_materials.router)
    app.include_router(similar_embeddings.router)
    app.include_router(demo_run.router)
    app.include_router(extraction_eval.router)
    app.include_router(community_cluster_graph.router)
    app.include_router(rag_checks.router)
    app.include_router(evidence_bbox.router)
    app.include_router(run_transparency.router)
    app.include_router(quality_board.router)
    app.include_router(arbiter_resolve.router)
    app.include_router(graph_encoding.router)
    app.include_router(kg_health.router)
    app.include_router(prose_claims.router)
    app.include_router(property_graph.router)
    app.include_router(unit_provenance.router)
    app.include_router(agent_trace.router)
    app.include_router(edge_anomalies.router)
