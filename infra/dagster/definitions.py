"""Dagster orchestration for the ingestion → KG → index → gap-scan pipeline (§9).

Optional: Dagster is not a hard dependency (the embedded profile orchestrates via
``ingestion_service.cli``). Install ``dagster dagster-webserver`` and run
``dagster dev -f infra/dagster/definitions.py`` to get the asset graph + schedules
(regular corpus refresh, §24.5/§24.16). Assets are thin wrappers over the same
library functions used by the CLI, so behavior is identical.
"""

# NB: no `from __future__ import annotations` — Dagster inspects the real
# `context` parameter type at runtime, and PEP 563 stringized annotations make
# its AssetExecutionContext check fail with DagsterInvalidDefinitionError.

try:
    from dagster import (  # type: ignore[import-not-found]
        AssetExecutionContext,
        Definitions,
        ScheduleDefinition,
        asset,
        define_asset_job,
    )

    _HAS_DAGSTER = True
except Exception:  # dagster optional
    _HAS_DAGSTER = False


if _HAS_DAGSTER:

    def _store():  # type: ignore[no-untyped-def]
        from kg_common import get_settings
        from kg_retrievers.graph_store import KuzuGraphStore

        return KuzuGraphStore(get_settings().kuzu_db_path)

    @asset
    def corpus_graph(context: AssetExecutionContext) -> dict:
        """Parse + extract + evidence-first upsert of the corpus (§5/§6/§9)."""
        from ingestion_service.cli import discover
        from ingestion_service.parsers import parse_document
        from ingestion_service.pipeline import IngestionPipeline

        from kg_common import get_settings
        from kg_retrievers.graph_store import KuzuGraphStore

        store = KuzuGraphStore(get_settings().kuzu_db_path)
        pipe = IngestionPipeline(store)
        for f in discover(get_settings().data_dir, max_mb=8)[:200]:
            parsed = parse_document(f)
            if parsed:
                pipe.ingest(parsed)
        counts = store.counts()
        store.close()
        context.log.info(f"graph={counts}")
        return counts

    @asset(deps=[corpus_graph])
    def search_index(context: AssetExecutionContext) -> dict:
        """Vector + keyword index over chunks (§4)."""
        from kg_retrievers.indexer import index_graph

        store = _store()
        out = index_graph(store)
        store.close()
        return out

    @asset(deps=[corpus_graph])
    def gap_scan(context: AssetExecutionContext) -> dict:
        """Gap + contradiction detection (§15)."""
        from kg_retrievers.gap_analysis import GapScanner

        store = _store()
        out = GapScanner(store).scan().as_dict()
        store.close()
        return out

    refresh_job = define_asset_job("corpus_refresh", selection="*")
    weekly = ScheduleDefinition(job=refresh_job, cron_schedule="0 3 * * 1")  # Mon 03:00

    defs = Definitions(
        assets=[corpus_graph, search_index, gap_scan],
        jobs=[refresh_job],
        schedules=[weekly],
    )
