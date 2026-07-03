"""Feature routers, attached by the API gateway app factory."""

from __future__ import annotations

from fastapi import FastAPI


def attach_routers(app: FastAPI) -> None:
    from api_gateway.routers import (
        admin,
        advise,
        auth,
        chat,
        comparison,
        contradictions,
        curation,
        documents,
        evidence,
        experiments,
        insights,
        export,
        gaps,
        graph,
        graph_ext,
        ingest,
        notifications,
        query,
        research,
        search,
        views,
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
