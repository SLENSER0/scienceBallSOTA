"""Dagster ``entity_resolution`` asset — §8.10 ER step in the pipeline graph.

Step 6 of the §9.1 flow (``NORMALIZE --> ER --> VALIDATE``). Thin wrapper over
:func:`ingestion_service.er_step.run_er_step`, so the asset graph runs exactly
the same ER library the CLI / API use. Upstream is ``corpus_graph`` (parse +
extract + upsert); downstream schema-validation / graph-upsert assets consume the
canonical ids this emits.

Kept in a separate module (not ``definitions.py``) so it can be wired in without
editing the hub. To register it, add to ``infra/dagster/definitions.py``::

    from er_asset import entity_resolution
    defs = Definitions(assets=[corpus_graph, search_index, gap_scan, entity_resolution], ...)

As with the rest of ``infra/dagster``, Dagster is optional: importing this module
without ``dagster`` installed yields ``entity_resolution = None`` and never
raises, so ``definitions.py`` can guard on it.
"""

# NB: no `from __future__ import annotations` — Dagster inspects the real
# `context` parameter type at runtime (matches definitions.py).

try:
    from dagster import (  # type: ignore[import-not-found]
        AssetExecutionContext,
        MetadataValue,
        asset,
    )

    _HAS_DAGSTER = True
except Exception:  # dagster optional
    _HAS_DAGSTER = False


def _resolve_corpus(store) -> dict:  # type: ignore[no-untyped-def]
    """Run the ER step over every supported entity type in the graph.

    The corpus assets have already upserted nodes, so here we resolve each type's
    canonical nodes against each other (full pass) to surface duplicate groups and
    their canonical id — the shape Step 7 upsert consumes. Uses ``ingestion``
    library code directly; returns a JSON-able report.
    """
    from ingestion_service.er_step import SUPPORTED_TYPES, pull_existing, resolve_incremental

    from kg_common import get_settings
    from kg_retrievers.store_factory import make_graph_store

    store = store or make_graph_store(get_settings())
    run_id = None
    all_decisions = []
    per_type: dict[str, int] = {}
    for etype in SUPPORTED_TYPES:
        nodes = pull_existing(store, etype)
        # Full pass: treat all canonicals as "new" against an empty baseline so the
        # resolver reports every duplicate group + its canonical id.
        decisions = resolve_incremental(etype, nodes, [], extraction_run_id=run_id)
        all_decisions.extend(decisions)
        if decisions:
            per_type[etype] = len(decisions)

    by_decision: dict[str, int] = {}
    for d in all_decisions:
        by_decision[d.decision] = by_decision.get(d.decision, 0) + 1
    canonical_ids = sorted({d.canonical_id for d in all_decisions})
    return {
        "n_decisions": len(all_decisions),
        "by_decision": by_decision,
        "per_type": per_type,
        "auto_merge": by_decision.get("auto_merge", 0),
        "review_needed": by_decision.get("review_needed", 0),
        "canonical_ids": canonical_ids,
    }


if _HAS_DAGSTER:

    @asset(deps=["corpus_graph"])
    def entity_resolution(context: AssetExecutionContext) -> dict:
        """ER Step 6 (§8.10): resolve corpus entities → canonical merge decisions."""
        from kg_common import get_settings
        from kg_retrievers.store_factory import make_graph_store

        store = make_graph_store(get_settings())
        try:
            report = _resolve_corpus(store)
        finally:
            close = getattr(store, "close", None)
            if callable(close):
                close()

        context.log.info(
            "entity_resolution decisions={} auto_merge={} review={}".format(
                report["n_decisions"], report["auto_merge"], report["review_needed"]
            )
        )
        context.add_output_metadata(
            {
                "decisions": report["n_decisions"],
                "auto_merge": report["auto_merge"],
                "review_needed": report["review_needed"],
                "canonical_ids": MetadataValue.int(len(report["canonical_ids"])),
                "per_type": MetadataValue.json(report["per_type"]),
            }
        )
        return report

else:  # dagster not installed → let definitions.py guard on a falsy attribute
    entity_resolution = None
