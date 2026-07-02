"""Schema versioning + migration guard (§3.15 / §23.4).

Maintains a singleton ``SchemaVersion`` node (version, applied_at, checksum,
linkml_version) and a fail-fast guard so a service refuses to start against an
unexpected schema. For the embedded profile the schema itself is created by
``KuzuGraphStore.ensure_schema``; this tracks its *version* + provenance.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema import EDGE_SCHEMA, NodeLabel

_log = get_logger("schema_version")
CURRENT_VERSION = "0.1.0"


def schema_checksum() -> str:
    """Stable checksum of the label/edge catalog — changes when the ontology does."""
    payload = "|".join(sorted(str(x) for x in NodeLabel))
    payload += "||" + "|".join(sorted(f"{f}:{r}:{t}" for f, r, t in EDGE_SCHEMA))
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


@dataclass
class SchemaStatus:
    current: str | None
    expected: str
    checksum: str
    up_to_date: bool


def apply_schema_version(
    store: KuzuGraphStore, *, version: str = CURRENT_VERSION, linkml_version: str = "0.1.0"
) -> SchemaStatus:
    """Idempotently record the current schema version + checksum."""
    store.upsert_node(
        "schema:version",
        "Finding",
        name=f"SchemaVersion {version}",
        text=f"schema_version={version}",
        schema_version=version,
        created_at="applied",
        review_status="accepted",
        checksum=schema_checksum(),
        linkml_version=linkml_version,
    )
    _log.info("schema.applied", version=version, checksum=schema_checksum())
    return migrate_status(store)


def migrate_status(store: KuzuGraphStore) -> SchemaStatus:
    nd = store.get_node("schema:version")
    current = nd.get("schema_version") if nd else None
    return SchemaStatus(
        current=current,
        expected=CURRENT_VERSION,
        checksum=schema_checksum(),
        up_to_date=current == CURRENT_VERSION and (nd or {}).get("checksum") == schema_checksum(),
    )


def check_schema_or_raise(store: KuzuGraphStore, *, expected: str = CURRENT_VERSION) -> None:
    """Fail-fast guard (§3.15): raise if the stored schema version mismatches."""
    st = migrate_status(store)
    if st.current is None:
        apply_schema_version(store, version=expected)
        return
    if st.current != expected:
        raise RuntimeError(
            f"schema version mismatch: store has {st.current}, service expects {expected} "
            "— run `make schema-gen` + migrations"
        )
