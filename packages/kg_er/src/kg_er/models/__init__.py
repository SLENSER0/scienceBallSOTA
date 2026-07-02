"""Per-entity-type Splink model specs (§8.4/§8.5)."""

from __future__ import annotations

from kg_er.models.base import ClusterResult, ModelSpec, model_card, predict_clusters, train_linker
from kg_er.models.registry import SUPPORTED_TYPES, get_model

__all__ = [
    "ModelSpec",
    "ClusterResult",
    "train_linker",
    "predict_clusters",
    "model_card",
    "get_model",
    "SUPPORTED_TYPES",
]
