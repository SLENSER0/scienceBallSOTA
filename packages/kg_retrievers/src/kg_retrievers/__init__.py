"""Graph / vector / keyword / hybrid retrievers + GraphRAG."""

from __future__ import annotations

from kg_retrievers.community import CommunityResult, detect_communities
from kg_retrievers.confidence_of_absence import (
    AbsenceAnalyzer,
    CoverageCell,
    ExtractorRecall,
)
from kg_retrievers.entity_index import EntityHit, EntityVectorIndex
from kg_retrievers.gap_analysis import GapScanner, ScanResult
from kg_retrievers.graph_retriever import GraphRetriever, RetrievalResult
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.hybrid import HybridRetriever
from kg_retrievers.indexer import index_graph
from kg_retrievers.keyword_store import KeywordStore
from kg_retrievers.schema_version import (
    apply_schema_version,
    check_schema_or_raise,
    migrate_status,
)
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
    "EntityVectorIndex",
    "EntityHit",
    "AbsenceAnalyzer",
    "CoverageCell",
    "ExtractorRecall",
    "apply_schema_version",
    "check_schema_or_raise",
    "migrate_status",
]
