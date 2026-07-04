"""Community-panel router tests (§17.9). Hermetic: a fake graph store stands in.

Doubles as a regression for the N+1 → single-scan optimisation: ``summaries()`` used
to run one full ``n.community_id=$c`` node scan *per community*; it now issues ONE
batched scan and groups in Python. The fake store counts each kind of scan, so we
prove (a) exactly one batched member scan and zero per-community scans per request,
and (b) the payload is byte-for-byte what the old per-community algorithm produced.
"""

from __future__ import annotations

import api_gateway.routers.community_panel as community_panel
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_FINDING = "Finding"

# (community_id, id, name, domain, label) — one Finding summary node included so the
# `n.label<>$f` filter is actually exercised (it must never appear as a member).
_NODES: list[tuple[int, str, str, str, str]] = [
    (1, "n1", "Осмос", "water", "Material"),
    (1, "n2", "Фильтр", "water", "Method"),
    (1, "n3", "Насос", "", "Equipment"),  # empty domain → excluded from the domain set
    (2, "n4", "Никель", "metallurgy", "Material"),
    (2, "n5", "", "metallurgy", "Material"),  # empty name → excluded from top_entities
    (3, "n6", "Одинокий", "x", "Material"),  # lone member → filtered by min_size>=2
    (1, "f1", "Мембраны", "", _FINDING),  # the community's own summary artifact
]

# (community_id, name, text) community-summary Finding rows.
_SUMMARIES: list[tuple[int, str, str]] = [
    (1, "Мембраны", "summary-1"),
    (2, "", "summary-2"),  # blank name → title falls back to "Кластер знаний #2"
    (3, "Small", "summary-3"),
]


class FakeStore:
    """Canned community subgraph honouring the router's read-templates, scan-counting."""

    def __init__(self) -> None:
        self.batched_scans = 0
        self.per_cid_scans = 0

    def rows(self, cypher: str, params: dict | None = None) -> list[list]:
        params = params or {}
        if "coalesce(f.text" in cypher:  # _read_summaries
            return [[c, name, text] for c, name, text in _SUMMARIES]
        if "RETURN n.community_id, n.id" in cypher:  # batched _members_by_community
            self.batched_scans += 1
            f = params["f"]
            return [[c, i, nm, d, lbl] for c, i, nm, d, lbl in _NODES if lbl != f]
        if "n.community_id=$c" in cypher:  # per-community _members (subgraph endpoint)
            self.per_cid_scans += 1
            c, f = params["c"], params["f"]
            return [[i, nm, d, lbl] for cc, i, nm, d, lbl in _NODES if cc == c and lbl != f]
        return []


def _expected(min_size: int, limit: int) -> list[dict]:
    """Reference payload computed with the ORIGINAL per-community algorithm."""
    out: list[dict] = []
    for cid, name, text in _SUMMARIES:
        members = [[i, nm, d, lbl] for c, i, nm, d, lbl in _NODES if c == cid and lbl != _FINDING]
        if len(members) < min_size:
            continue
        domains = sorted({str(d) for _, _, d, _ in members if d})
        top_entities = [nm for _, nm, _, _ in members if nm][:8]
        out.append(
            {
                "community_id": cid,
                "title": name or f"Кластер знаний #{cid}",
                "summary": text,
                "size": len(members),
                "domains": domains,
                "top_entities": top_entities,
                "member_ids": [mid for mid, *_ in members],
            }
        )
    out.sort(key=lambda c: c["size"], reverse=True)
    return out[:limit]


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def client(store: FakeStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(community_panel, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(community_panel.router)
    return TestClient(app)


def test_summaries_payload_matches_old_algorithm(client: TestClient) -> None:
    """Batched grouping yields exactly the old per-community payload (behavior-preserving)."""
    body = client.get("/api/v1/graph-communities/summaries").json()
    expected = _expected(min_size=2, limit=30)
    assert body == {"count": len(expected), "communities": expected}


def test_summaries_runs_one_batched_scan_no_per_cid(client: TestClient, store: FakeStore) -> None:
    """The panel does ONE batched member scan and zero per-community scans (N+1 removed)."""
    client.get("/api/v1/graph-communities/summaries")
    assert store.batched_scans == 1
    assert store.per_cid_scans == 0


def test_summaries_min_size_filter(client: TestClient) -> None:
    """min_size still drops smaller clusters exactly as before, over the batched data."""
    body = client.get("/api/v1/graph-communities/summaries", params={"min_size": 3}).json()
    assert body == {
        "count": 1,
        "communities": _expected(min_size=3, limit=30),
    }
    # Only community 1 (size 3) clears a min_size of 3.
    assert [c["community_id"] for c in body["communities"]] == [1]


def test_summaries_finding_node_never_a_member(client: TestClient) -> None:
    """The community's own Finding summary node is excluded from members/ids/entities."""
    communities = client.get("/api/v1/graph-communities/summaries").json()["communities"]
    c1 = next(c for c in communities if c["community_id"] == 1)
    assert "f1" not in c1["member_ids"]
    assert c1["size"] == 3
    assert c1["top_entities"] == ["Осмос", "Фильтр", "Насос"]
    assert c1["domains"] == ["water"]


def test_summaries_title_fallback_and_sorted_by_size(client: TestClient) -> None:
    """Blank-name cluster gets the fallback title; entries are ordered largest-first."""
    communities = client.get("/api/v1/graph-communities/summaries").json()["communities"]
    assert [c["community_id"] for c in communities] == [1, 2]  # size 3 then size 2
    c2 = next(c for c in communities if c["community_id"] == 2)
    assert c2["title"] == "Кластер знаний #2"
    assert c2["top_entities"] == ["Никель"]  # the empty-name member is skipped
