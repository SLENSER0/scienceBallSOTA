"""Edge provenance reader over the Kuzu ``Rel`` table (§8.11).

Every relationship (ребро) in the KG carries provenance so a claim can be audited
(§3.6/§3.7): the ``Evidence`` ids it was read from, the extraction run (прогон
извлечения) that emitted it, and two review flags — whether the edge was *inferred*
rather than directly extracted, and whether it has been *contradicted* by other
evidence.

This module exposes a single read-only lookup, :func:`edge_provenance`, that fetches
one directed edge ``(src)-[rel_type]->(dst)`` off a :class:`KuzuGraphStore` and rolls
its provenance columns into a frozen :class:`EdgeProvenance` record.

Unlike custom *node* props (which live in the JSON ``props`` catch-all and are not
queryable), these edge fields are declared columns of the ``Rel`` table
(``REL_COLUMNS`` in :mod:`kg_retrievers.graph_store`), so Cypher can ``RETURN`` them
as base relationship columns directly. ``evidence_ids`` is persisted as a JSON string
by :meth:`KuzuGraphStore.upsert_edge`, so it is parsed back into a tuple here. The
module never writes and never raises on a missing edge — it returns ``None``.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("edge_provenance")


@dataclass(frozen=True)
class EdgeProvenance:
    """Provenance of one directed KG relationship / edge (ребро) (§8.11).

    Attributes:
        src: id of the source node the edge starts at (источник).
        dst: id of the destination node the edge points to (цель).
        rel_type: the relationship type stamped on the edge (тип связи).
        evidence_ids: ordered ``Evidence`` ids the edge was read from (эвиденс),
            empty when the edge carries no evidence.
        extractor_run_id: the extraction run (прогон) that emitted the edge, or
            ``None`` when the edge carries no run stamp.
        inferred: ``True`` when the edge was inferred rather than directly extracted
            (выведено) — dashed edge in the UI (§5.2.3).
        contradicted: ``True`` when the edge is contradicted by other evidence
            (опровергнуто) — red edge in the UI (§5.2.3).
    """

    src: str
    dst: str
    rel_type: str
    evidence_ids: tuple[str, ...]
    extractor_run_id: str | None
    inferred: bool
    contradicted: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict (copies the id tuple to a list)."""
        return {
            "src": self.src,
            "dst": self.dst,
            "rel_type": self.rel_type,
            "evidence_ids": list(self.evidence_ids),
            "extractor_run_id": self.extractor_run_id,
            "inferred": self.inferred,
            "contradicted": self.contradicted,
        }


def _parse_evidence_ids(raw: Any) -> tuple[str, ...]:
    """Coerce a stored ``evidence_ids`` cell into an ordered tuple of ids.

    The store persists the list as a JSON string; older / direct writes may leave a
    native list. Anything unparseable or empty degrades to an empty tuple.
    """
    if isinstance(raw, str) and raw:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return tuple(str(x) for x in parsed)
    elif isinstance(raw, list):
        return tuple(str(x) for x in raw)
    return ()


def edge_provenance(
    store: KuzuGraphStore, src: str, dst: str, rel_type: str
) -> EdgeProvenance | None:
    """Read the provenance of the ``(src)-[rel_type]->(dst)`` edge (§8.11).

    Matches the single directed relationship of type ``rel_type`` between the two
    nodes and rolls its provenance columns (``evidence_ids``, ``extractor_run_id``,
    ``inferred``, ``contradicted``) into an :class:`EdgeProvenance`. These are base
    columns of the ``Rel`` table, so they are ``RETURN``ed directly; ``evidence_ids``
    is parsed from its stored JSON form. Unset boolean flags read back as ``None`` and
    are coerced to ``False``.

    Returns ``None`` when no such edge exists — an unknown ``src`` / ``dst`` or a
    ``rel_type`` that no edge between them carries — never an error.
    """
    rows = store.rows(
        "MATCH (a:Node {id:$src})-[r:Rel]->(b:Node {id:$dst}) "
        "WHERE r.type=$rtype "
        "RETURN r.evidence_ids, r.extractor_run_id, r.inferred, r.contradicted "
        "LIMIT 1",
        {"src": src, "dst": dst, "rtype": rel_type},
    )
    if not rows:
        _log.info("edge_provenance.miss", src=src, dst=dst, rel_type=rel_type)
        return None

    eids_raw, run_id, inferred_raw, contradicted_raw = rows[0]
    return EdgeProvenance(
        src=src,
        dst=dst,
        rel_type=rel_type,
        evidence_ids=_parse_evidence_ids(eids_raw),
        extractor_run_id=run_id,
        inferred=bool(inferred_raw),
        contradicted=bool(contradicted_raw),
    )
