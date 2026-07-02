"""kg_er — entity resolution for Material/Equipment/Person/Lab via Splink (§8).

Backend is DuckDB (in-process, ADR §8.1). Public API:

    from kg_er import resolve, build_er_frame, get_model
    result = resolve("Material", mentions)          # -> ResolveResult
    result.summary()                                # decision counts
"""

from __future__ import annotations

from kg_er.decision.engine import MergeProposal, build_proposals, decide, thresholds_for
from kg_er.decision.property_mapper import PropertyMapper, PropertyMapping
from kg_er.models.base import ClusterResult, ModelSpec, predict_clusters, train_linker
from kg_er.models.registry import SUPPORTED_TYPES, get_model
from kg_er.pipeline import ResolveResult, build_er_frame, resolve
from kg_er.store.property_vocab import PropertyVocabulary, default_vocabulary

__version__ = "0.1.0"

__all__ = [
    "resolve",
    "build_er_frame",
    "ResolveResult",
    "get_model",
    "SUPPORTED_TYPES",
    "ModelSpec",
    "ClusterResult",
    "train_linker",
    "predict_clusters",
    "decide",
    "thresholds_for",
    "MergeProposal",
    "build_proposals",
    "PropertyMapper",
    "PropertyMapping",
    "PropertyVocabulary",
    "default_vocabulary",
]
