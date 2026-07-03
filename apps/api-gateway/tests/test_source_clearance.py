"""[DE] Role-based source filtering at the read boundary (§17.1).

Proves the gateway does not return data from a source above the caller's clearance:
the evidence inspector 403s, and entity search silently drops the disallowed
entities — so «модель не отдаёт информацию из запрещённого источника».
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from api_gateway.routers import evidence, search
from fastapi import HTTPException

from kg_retrievers.graph_store import KuzuGraphStore


def _seeded_store() -> KuzuGraphStore:
    s = KuzuGraphStore(str(Path(tempfile.mkdtemp()) / "g"))
    s.upsert_node("mat_pub", "Material", name="Public Alloy", confidentiality_level="public")
    s.upsert_node("mat_int", "Material", name="Internal Alloy", confidentiality_level="internal")
    s.upsert_node(
        "mat_res", "Material", name="Restricted Alloy", confidentiality_level="restricted"
    )
    s.upsert_node(
        "ev_res", "Evidence", doc_id="d1", text="secret result", confidentiality_level="restricted"
    )
    return s


def test_evidence_read_403s_below_clearance(monkeypatch) -> None:
    s = _seeded_store()
    monkeypatch.setattr(evidence, "get_store", lambda: s)
    try:
        # curator / admin may read the restricted source
        assert evidence.get_evidence("ev_res", role="curator")["evidence_id"] == "ev_res"
        assert evidence.get_evidence("ev_res", role="admin")["evidence_id"] == "ev_res"
        # researcher / analyst / external_partner may not
        for role in ("researcher", "analyst", "external_partner"):
            with pytest.raises(HTTPException) as ei:
                evidence.get_evidence("ev_res", role=role)
            assert ei.value.status_code == 403
    finally:
        s.close()


def test_entity_search_filters_by_clearance(monkeypatch) -> None:
    s = _seeded_store()
    monkeypatch.setattr(search, "get_store", lambda: s)
    try:

        def ids(role: str) -> set[str]:
            res = search.entity_search(q="alloy", type=None, limit=50, role=role)
            return {r["id"] for r in res["results"]}

        assert ids("external_partner") == {"mat_pub"}  # public only
        assert ids("researcher") == {"mat_pub", "mat_int"}  # + internal
        assert ids("analyst") == {"mat_pub", "mat_int"}
        assert ids("admin") == {"mat_pub", "mat_int", "mat_res"}  # + restricted
    finally:
        s.close()
