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
        apples,
        auth,
        benchmark,
        chat,
        chat_absence,
        community_panel,
        comparison,
        contradictions,
        corpus_overview,
        coverage_heatmap,
        curation,
        documents,
        entity_resolution,
        er_candidates,
        evidence,
        evidence_pack,
        experiments,
        export,
        figures,
        gap_closure,
        gaps,
        gds_live,
        graph,
        graph_ext,
        hardness,
        hitl,
        ingest,
        insights,
        link_prediction,
        missing_links,
        mp_authority,
        notifications,
        query,
        research,
        search,
        similarity_links,
        source_trust,
        table_cell,
        views,
        voi,
    )

    app.include_router(auth.router)
    app.include_router(query.router)
    app.include_router(comparison.router)
    app.include_router(notifications.router)
    app.include_router(graph.router)
    app.include_router(graph.entities_router)
    app.include_router(search.router)
    app.include_router(evidence.router)
    app.include_router(admin.router)
    app.include_router(export.router)
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
    # --- batch 1 roadmap features ---
    app.include_router(table_cell.router)
    app.include_router(er_candidates.router)
    app.include_router(mp_authority.router)
    app.include_router(absence.router)
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
