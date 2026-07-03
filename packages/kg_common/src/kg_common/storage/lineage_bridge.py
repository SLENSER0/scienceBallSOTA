"""Bridge the MetadataCatalog lineage graph to OpenLineage events (§10.5/§10.9).

Reads recorded lineage edges from a :class:`~kg_common.storage.metadata_catalog.
MetadataCatalog` and renders them as an OpenLineage RunEvent, so pipeline runs
registered in the embedded catalog can be exported to a Marquez/OpenLineage
backend without changing either module.
"""

from __future__ import annotations

from typing import Any

from kg_common.lineage_openlineage import from_lineage_edges
from kg_common.storage.metadata_catalog import MetadataCatalog


def emit_catalog_lineage(
    catalog: MetadataCatalog,
    *,
    job_name: str,
    run_id: str,
    event_time: str,
    asset: str | None = None,
) -> dict[str, Any]:
    """Render the catalog's lineage (optionally for one asset) as an OpenLineage event."""
    edges = catalog.lineage_for(asset) if asset else catalog.list_lineage()
    return from_lineage_edges(edges, run_id=run_id, job_name=job_name, event_time=event_time)
