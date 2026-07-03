"""§4/§12 retrieval-factory selects the hybrid backend by runtime profile."""

from __future__ import annotations

import pytest

from kg_retrievers import retrieval_factory as rf
from kg_retrievers.hybrid import HybridRetriever


class _S:
    def __init__(self, profile: str) -> None:
        self.runtime_profile = profile


def test_embedded_profile_uses_open_default(monkeypatch):
    monkeypatch.setattr(rf, "get_settings", lambda: _S("embedded"))
    h = rf.make_hybrid_retriever()
    assert isinstance(h, HybridRetriever)


def test_server_profile_wraps_server_stores(monkeypatch):
    monkeypatch.setattr(rf, "get_settings", lambda: _S("server"))
    try:
        h = rf.make_hybrid_retriever()
    except Exception as exc:  # servers not up in this env
        pytest.skip(f"server stores unreachable: {type(exc).__name__}")
    assert isinstance(h, HybridRetriever)
    # When the live servers are reachable each channel is a _StoreAdapter.
    if h.vector is not None:
        assert type(h.vector).__name__ == "_StoreAdapter"
    if h.keyword is not None:
        assert type(h.keyword).__name__ == "_StoreAdapter"
