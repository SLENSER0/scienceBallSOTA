"""Shared Splink model scaffolding (§8.4/§8.5).

Wraps SettingsCreator + deterministic training (fixed seeds §8.1) and a
``predict`` that aggregates pairs into transitive clusters (connected
components) — the shape the decision engine (§8.7) consumes.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from splink import DuckDBAPI, Linker, SettingsCreator

RANDOM_SEED = 42


@dataclass
class ModelSpec:
    """Declarative Splink model spec for one entity type."""

    entity_type: str
    comparisons: list
    blocking_rules: list
    deterministic_rules: list
    em_training_blocks: list
    link_type: str = "dedupe_only"
    retain_intermediate: bool = False


@dataclass
class ClusterResult:
    """Transitive cluster of records + the strongest supporting pair score."""

    members: tuple[str, ...]
    max_probability: float
    pair_probabilities: dict[tuple[str, str], float] = field(default_factory=dict)


def _union_find(pairs: Sequence[tuple[str, str]]) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return parent


def train_linker(spec: ModelSpec, df: pd.DataFrame) -> Linker:
    """Build + deterministically train a Splink linker for *df*.

    On small datasets the deterministic-rule recall estimate cannot converge, so
    we fall back to a fixed prior — the u/m estimates still shape the model.
    """
    settings = SettingsCreator(
        link_type=spec.link_type,
        blocking_rules_to_generate_predictions=spec.blocking_rules,
        comparisons=spec.comparisons,
        retain_intermediate_calculation_columns=spec.retain_intermediate,
        # Prior; overwritten by the deterministic-rule estimate when it converges.
        probability_two_random_records_match=0.01,
    )
    linker = Linker(df, settings, db_api=DuckDBAPI())
    # §8.4: probability two random records match, then u by sampling, then m by EM.
    with contextlib.suppress(ValueError):  # tiny dataset — keep the fixed prior above
        linker.training.estimate_probability_two_random_records_match(
            spec.deterministic_rules, recall=0.9
        )
    linker.training.estimate_u_using_random_sampling(max_pairs=5e5, seed=RANDOM_SEED)
    for block in spec.em_training_blocks:
        try:
            linker.training.estimate_parameters_using_expectation_maximisation(block)
        except Exception:
            continue  # a block may have too few pairs to estimate m; skip it
    return linker


def predict_clusters(
    linker: Linker, threshold: float = 0.5
) -> tuple[list[ClusterResult], pd.DataFrame]:
    """Predict pairs above *threshold* and aggregate into transitive clusters."""
    preds = linker.inference.predict(threshold_match_probability=threshold)
    pdf = preds.as_pandas_dataframe()
    pairs: list[tuple[str, str]] = []
    pair_prob: dict[tuple[str, str], float] = {}
    for _, row in pdf.iterrows():
        a, b = str(row["unique_id_l"]), str(row["unique_id_r"])
        key = (a, b) if a <= b else (b, a)
        pairs.append(key)
        pair_prob[key] = float(row["match_probability"])

    parent = _union_find(pairs)
    groups: dict[str, set[str]] = {}
    for node in parent:
        root = node
        while parent[root] != root:
            root = parent[root]
        groups.setdefault(root, set()).add(node)

    clusters: list[ClusterResult] = []
    for members in groups.values():
        member_tuple = tuple(sorted(members))
        rel = {k: v for k, v in pair_prob.items() if k[0] in members and k[1] in members}
        clusters.append(
            ClusterResult(
                members=member_tuple,
                max_probability=max(rel.values()) if rel else 0.0,
                pair_probabilities=rel,
            )
        )
    return clusters, pdf


def model_card(spec: ModelSpec, df: pd.DataFrame, trained_at: str) -> dict[str, Any]:
    """Serializable model card (§8.4): seed, train size, comparisons."""
    return {
        "entity_type": spec.entity_type,
        "link_type": spec.link_type,
        "random_seed": RANDOM_SEED,
        "train_rows": len(df),
        "n_comparisons": len(spec.comparisons),
        "n_blocking_rules": len(spec.blocking_rules),
        "trained_at": trained_at,
    }
