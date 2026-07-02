"""Graph / vector / keyword / hybrid retrievers + GraphRAG."""

from __future__ import annotations

from kg_retrievers.community import CommunityResult, detect_communities
from kg_retrievers.gap_analysis import GapScanner, ScanResult
from kg_retrievers.graph_retriever import GraphRetriever, RetrievalResult
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.hybrid import HybridRetriever
from kg_retrievers.indexer import index_graph
from kg_retrievers.keyword_store import KeywordStore
from kg_retrievers.vector_store import VectorStore

__version__ = "0.1.0"

__all__ = [
    "KuzuGraphStore",
    "GraphRetriever",
    "RetrievalResult",
    "VectorStore",
    "KeywordStore",
    "HybridRetriever",
    "index_graph",
    "GapScanner",
    "ScanResult",
    "detect_communities",
    "CommunityResult",
]
