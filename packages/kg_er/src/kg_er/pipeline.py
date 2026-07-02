"""End-to-end ER pipeline: mentions -> features -> Splink -> proposals (§8.3/§8.7).

``build_er_frame`` assembles the per-type feature DataFrame; ``resolve`` trains
the model, predicts clusters, and applies the decision engine. Designed to be
called from the ingestion pipeline and the Dagster ER asset (§8.10).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from kg_er.decision.engine import MergeProposal, build_proposals
from kg_er.deterministic import SPLINK_MIN_ROWS, deterministic_clusters
from kg_er.features import build_row
from kg_er.models.base import ClusterResult, model_card, predict_clusters, train_linker
from kg_er.models.registry import get_model


def build_er_frame(entity_type: str, mentions: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Assemble a deterministic feature DataFrame for *entity_type*.

    Each mention must carry ``unique_id``. Rows are sorted by unique_id so Splink
    training and downstream diffs are stable.
    """
    rows = [build_row(entity_type, m) for m in mentions]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("unique_id").reset_index(drop=True)
    return df


@dataclass
class ResolveResult:
    entity_type: str
    clusters: list[ClusterResult]
    proposals: list[MergeProposal]
    model_card: dict[str, Any]
    n_input: int

    def summary(self) -> dict[str, Any]:
        by_decision: dict[str, int] = {}
        for p in self.proposals:
            by_decision[p.decision.value] = by_decision.get(p.decision.value, 0) + 1
        return {
            "entity_type": self.entity_type,
            "n_input": self.n_input,
            "n_clusters": len([c for c in self.clusters if len(c.members) > 1]),
            "decisions": by_decision,
        }


def resolve(
    entity_type: str,
    mentions: Sequence[dict[str, Any]],
    *,
    threshold: float = 0.5,
    reviewed_ids: frozenset[str] = frozenset(),
    trained_at: str = "unspecified",
    backend: str = "auto",
) -> ResolveResult:
    """Run the full ER pipeline for one entity type.

    ``backend``: ``"auto"`` (default) uses deterministic scoring below
    :data:`~kg_er.deterministic.SPLINK_MIN_ROWS` rows — where Splink's EM cannot
    converge — and trained Splink above it; ``"splink"`` / ``"deterministic"``
    force one path. The deterministic path falls back automatically if Splink
    training raises.
    """
    spec = get_model(entity_type)
    df = build_er_frame(entity_type, mentions)
    card = model_card(spec, df, trained_at)
    if len(df) < 2:
        card["backend"] = "trivial"
        return ResolveResult(entity_type, [], [], card, len(df))

    use_splink = backend == "splink" or (backend == "auto" and len(df) >= SPLINK_MIN_ROWS)
    clusters: list[ClusterResult]
    if use_splink:
        try:
            linker = train_linker(spec, df)
            clusters, _ = predict_clusters(linker, threshold=threshold)
            card["backend"] = "splink"
        except Exception:
            clusters = deterministic_clusters(
                entity_type, df.to_dict("records"), threshold=threshold
            )
            card["backend"] = "deterministic_fallback"
    else:
        clusters = deterministic_clusters(entity_type, df.to_dict("records"), threshold=threshold)
        card["backend"] = "deterministic"

    proposals = build_proposals(entity_type, clusters, reviewed_ids=reviewed_ids)
    return ResolveResult(
        entity_type=entity_type,
        clusters=clusters,
        proposals=proposals,
        model_card=card,
        n_input=len(df),
    )
