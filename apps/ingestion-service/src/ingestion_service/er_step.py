"""§8.10 — incremental entity-resolution step for the ingestion pipeline.

Sits between NORMALIZE (Step 5) and VALIDATE (Step 7) in the §9.1 flow
``NORMALIZE --> ER --> VALIDATE``. It wraps :func:`kg_er.resolve` and runs it
*incrementally*: the mentions extracted from a freshly-ingested document are
resolved against the canonical entities already present in the graph (blocking
by ``label``), **without retraining** the Splink model. Auto-merge groups that
link a new mention to an existing canonical become merge plans, so Step 7 upserts
by the existing canonical id instead of minting a duplicate node.

Design notes
------------
* **No hard dependency on Splink/duckdb at import time** — :func:`kg_er.resolve`
  is imported lazily inside the functions, and every call is wrapped so ER can
  never crash the ingestion pipeline (``review_needed``/``separate`` must not
  block; §8.10 acceptance).
* **Existing-canonical preference.** :func:`kg_er.decision.engine.build_proposals`
  picks ``min(members)`` as the representative. For the incremental step we
  override that: when a proposal's cluster already contains a canonical node from
  the graph, that existing id becomes the merge target so the new mention folds
  *into* it (this is what makes ``AA2024`` merge to ``material:al-cu-2024``).
* **Provenance.** ``extraction_run_id`` is threaded through every decision so
  Step 7 / curation merge events can reference the run (§9.2 Step 7 / §8.10).

The module is deliberately store-agnostic: it reads via the shared
``store.rows`` / ``store._node_dict`` interface (Kuzu embedded or Neo4j server
profile) and returns *plans* — applying the merges is the caller's job (the API
gateway reuses the tested ``CurationService.merge_entities``; the Dagster asset
runs report-only).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

# kg_er entity types with a feature builder + Splink/deterministic spec (§8.4).
SUPPORTED_TYPES: tuple[str, ...] = (
    "Material",
    "Alloy",
    "Equipment",
    "Person",
    "Lab",
    "ResearchTeam",
)

# Cap on canonical nodes pulled per type per run — keeps the incremental compare
# bounded and, for typical graph sizes, on the deterministic scoring path (§8.5).
_MAX_EXISTING = 500


# --------------------------------------------------------------------------- #
# Config (§8.10: incremental inference vs scheduled retraining are separate)   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ERStepConfig:
    """Runtime knobs for the ingestion ER step.

    ``incremental`` — resolve new mentions against existing canonicals without
    retraining (the default hot path). ``retrain_on_schedule`` — a flag consumed
    by the Dagster retrain schedule, *not* by per-document inference, so model
    (re)training is decoupled from ingestion latency.
    """

    incremental: bool = True
    retrain_on_schedule: bool = False
    threshold: float = 0.5
    max_existing: int = _MAX_EXISTING

    @classmethod
    def from_env(cls) -> ERStepConfig:
        def _flag(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            incremental=_flag("ER_INCREMENTAL", True),
            retrain_on_schedule=_flag("ER_RETRAIN_ON_SCHEDULE", False),
            threshold=float(os.getenv("ER_THRESHOLD", "0.5")),
            max_existing=int(os.getenv("ER_MAX_EXISTING", str(_MAX_EXISTING))),
        )


# --------------------------------------------------------------------------- #
# Decision record (§9.2 Step 6 `ERDecision` shape)                            #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ERDecision:
    """One entity-resolution decision over a mention group.

    ``merge_to_existing`` is the §8.10 signal: an ``auto_merge`` group that folds
    at least one *new* mention into an existing canonical — Step 7 must upsert by
    ``canonical_id`` (no duplicate).
    """

    candidate_id: str
    entity_type: str
    decision: str
    match_probability: float
    canonical_id: str
    members: list[str]
    new_members: list[str]
    existing_members: list[str]
    merge_to_existing: bool
    blocked_by_review: bool = False
    extraction_run_id: str | None = None

    def drops(self) -> list[str]:
        """Member ids that fold into ``canonical_id`` on an auto-merge."""
        return [m for m in self.members if m != self.canonical_id]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "entity_type": self.entity_type,
            "decision": self.decision,
            "match_probability": round(self.match_probability, 4),
            "canonical_id": self.canonical_id,
            "members": list(self.members),
            "new_members": list(self.new_members),
            "existing_members": list(self.existing_members),
            "merge_to_existing": self.merge_to_existing,
            "blocked_by_review": self.blocked_by_review,
            "extraction_run_id": self.extraction_run_id,
        }


@dataclass(slots=True)
class ERStepReport:
    """Aggregate of one ER step over one document / batch."""

    extraction_run_id: str | None
    decisions: list[ERDecision] = field(default_factory=list)

    def by_decision(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.decisions:
            out[d.decision] = out.get(d.decision, 0) + 1
        return out

    def merge_plan(self) -> list[tuple[str, str, ERDecision]]:
        """(keep_id, drop_id, decision) pairs for every auto-merge fold.

        Only ``auto_merge`` decisions produce merges; ``review_needed`` and
        ``separate`` are returned in the report but never block the pipeline.
        """
        plan: list[tuple[str, str, ERDecision]] = []
        for d in self.decisions:
            if d.decision != "auto_merge" or d.blocked_by_review:
                continue
            for drop in d.drops():
                plan.append((d.canonical_id, drop, d))
        return plan

    def as_dict(self) -> dict[str, Any]:
        plan = self.merge_plan()
        return {
            "extraction_run_id": self.extraction_run_id,
            "n_decisions": len(self.decisions),
            "by_decision": self.by_decision(),
            "merges_planned": len(plan),
            "merges_to_existing": sum(1 for d in self.decisions if d.merge_to_existing),
            "decisions": [d.as_dict() for d in self.decisions],
        }


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _candidate_id(entity_type: str, members: Sequence[str]) -> str:
    """Order-independent stable id for a merge group (keys the review UI)."""
    digest = hashlib.sha1("|".join(sorted(members)).encode("utf-8")).hexdigest()[:12]
    return f"cand:{entity_type.lower()}:{digest}"


def node_to_mention(nd: dict[str, Any]) -> dict[str, Any] | None:
    """Project a graph node dict onto the kg_er mention shape (``unique_id``)."""
    nid = nd.get("id")
    if not nid:
        return None
    return {
        "unique_id": nid,
        "name": nd.get("name") or nd.get("canonical_name"),
        "formula": nd.get("formula") or nd.get("normalized_formula"),
        "designation": nd.get("designation") or nd.get("designation_code"),
        "alloy_family": nd.get("alloy_family"),
        "manufacturer": nd.get("manufacturer"),
        "model": nd.get("model") or nd.get("model_code"),
        "equipment_class": nd.get("equipment_class"),
        "orcid": nd.get("orcid"),
        "email": nd.get("email"),
        "org": nd.get("org") or nd.get("organization"),
        "city": nd.get("city"),
        "country": nd.get("country"),
        "_review_status": nd.get("review_status"),
    }


def pull_existing(
    store: Any, entity_type: str, *, cap: int = _MAX_EXISTING
) -> list[dict[str, Any]]:
    """Blocking step: pull existing canonical nodes of *entity_type* as mentions.

    Uses the shared ``label``-tagged node convention so it works on both the Kuzu
    embedded store and the Neo4j server-profile store (§8.10 incremental mode:
    compare new mentions only against existing canonical, no retraining).
    """
    try:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label = $label AND n.name IS NOT NULL RETURN n LIMIT $cap",
            {"label": entity_type, "cap": int(cap)},
        )
    except Exception:  # pragma: no cover - store dialect differences must not crash ER
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            nd = store._node_dict(r[0])
        except Exception:  # pragma: no cover
            continue
        m = node_to_mention(nd)
        if m:
            out.append(m)
    return out


def _reviewed_ids(mentions: Sequence[dict[str, Any]]) -> frozenset[str]:
    """Canonicals a curator locked — protected from silent auto-merge (§8.9)."""
    return frozenset(
        m["unique_id"]
        for m in mentions
        if m.get("_review_status") in {"accepted", "corrected"}
    )


# --------------------------------------------------------------------------- #
# Core: incremental resolve                                                    #
# --------------------------------------------------------------------------- #
def resolve_incremental(
    entity_type: str,
    new_mentions: Sequence[dict[str, Any]],
    existing_mentions: Sequence[dict[str, Any]],
    *,
    threshold: float = 0.5,
    extraction_run_id: str | None = None,
) -> list[ERDecision]:
    """Resolve *new* mentions against *existing* canonicals for one type.

    Returns an :class:`ERDecision` for every merge group that touches at least
    one new mention. Groups made only of pre-existing canonicals are left to the
    §8.8 review path — this step is about what the new document introduced.

    Never raises: if :func:`kg_er.resolve` errors, an empty list is returned so
    the ingestion pipeline continues (§8.10: ER must not block).
    """
    if entity_type not in SUPPORTED_TYPES or not new_mentions:
        return []

    new_ids = {m["unique_id"] for m in new_mentions}
    existing_ids = {m["unique_id"] for m in existing_mentions}
    combined = [*existing_mentions, *new_mentions]
    if len(combined) < 2:
        return []

    try:
        from kg_er import resolve  # lazy: heavy Splink/duckdb import
    except Exception:  # pragma: no cover - kg_er optional in some envs
        return []

    reviewed = _reviewed_ids(combined)
    try:
        result = resolve(
            entity_type, combined, threshold=threshold, reviewed_ids=reviewed
        )
        proposals = result.proposals
    except Exception:  # pragma: no cover - ER never blocks ingestion
        return []

    decisions: list[ERDecision] = []
    for p in proposals:
        members = list(p.members)
        member_set = set(members)
        new_in = sorted(member_set & new_ids)
        if not new_in:
            continue  # only-existing group → review path, not this step
        existing_in = sorted(member_set & existing_ids)
        # Prefer an existing canonical as the merge target so new folds into it;
        # else fold intra-document duplicates into the lexicographically-first new id.
        canonical = existing_in[0] if existing_in else min(members)
        decisions.append(
            ERDecision(
                candidate_id=_candidate_id(entity_type, members),
                entity_type=entity_type,
                decision=p.decision.value,
                match_probability=p.probability,
                canonical_id=canonical,
                members=sorted(members),
                new_members=new_in,
                existing_members=existing_in,
                merge_to_existing=bool(existing_in and new_in),
                blocked_by_review=p.blocked_by_review,
                extraction_run_id=extraction_run_id,
            )
        )
    return decisions


def run_er_step(
    mentions_by_type: dict[str, Sequence[dict[str, Any]]],
    store: Any,
    *,
    extraction_run_id: str | None = None,
    config: ERStepConfig | None = None,
) -> ERStepReport:
    """Run the incremental ER step over a document's normalized mentions.

    ``mentions_by_type`` maps an entity type to the new mentions extracted from
    the current document (each carrying ``unique_id``). For every supported type
    the existing canonicals are pulled from *store* (blocking) and the new
    mentions resolved against them. The returned :class:`ERStepReport` carries
    the per-group decisions plus a merge plan Step 7 applies by canonical id.
    """
    cfg = config or ERStepConfig.from_env()
    report = ERStepReport(extraction_run_id=extraction_run_id)
    for entity_type, new_mentions in mentions_by_type.items():
        if entity_type not in SUPPORTED_TYPES or not new_mentions:
            continue
        existing = (
            pull_existing(store, entity_type, cap=cfg.max_existing)
            if cfg.incremental
            else []
        )
        # Exclude any existing rows that share an id with the new batch (idempotent re-ingest).
        new_ids = {m["unique_id"] for m in new_mentions}
        existing = [m for m in existing if m["unique_id"] not in new_ids]
        report.decisions.extend(
            resolve_incremental(
                entity_type,
                new_mentions,
                existing,
                threshold=cfg.threshold,
                extraction_run_id=extraction_run_id,
            )
        )
    return report


# --------------------------------------------------------------------------- #
# Apply (optional): fold auto-merge drops into their canonical                 #
# --------------------------------------------------------------------------- #
def apply_merges(
    report: ERStepReport,
    merge_fn: Any,
    *,
    actor: str = "er_step",
) -> list[dict[str, Any]]:
    """Apply the report's auto-merge plan via a ``merge_fn(keep, drop, actor, reason)``.

    ``merge_fn`` is injected (the API gateway passes
    ``CurationService.merge_entities``) so this module stays free of a
    curation-service dependency. Each fold is best-effort: a failing merge is
    recorded and skipped, never raised — ER must not break ingestion (§8.10).
    Returns one result dict per attempted fold.
    """
    results: list[dict[str, Any]] = []
    for keep_id, drop_id, dec in report.merge_plan():
        reason = (
            f"ER auto_merge p={dec.match_probability:.3f} "
            f"run={dec.extraction_run_id or 'n/a'} cand={dec.candidate_id}"
        )
        try:
            merge_fn(keep_id, drop_id, actor=actor, reason=reason)
            results.append(
                {
                    "keep_id": keep_id,
                    "drop_id": drop_id,
                    "candidate_id": dec.candidate_id,
                    "status": "merged",
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            results.append(
                {
                    "keep_id": keep_id,
                    "drop_id": drop_id,
                    "candidate_id": dec.candidate_id,
                    "status": "error",
                    "error": str(exc),
                }
            )
    return results
