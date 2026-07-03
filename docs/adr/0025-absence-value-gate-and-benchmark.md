# ADR 0025: Confidence-of-absence value gate, benchmark & the N1–N3 flags (§33)

- **Status:** accepted
- **Date:** 2026-07-03

## Context

The confidence-of-absence layer (§25) already distinguishes `present` / `covered`
/ `retracted` / `possible_miss` / `genuine_gap` / `abstain` with a Bayesian
posterior and Beta-smoothed empirical recall priors. What it could not do was tell
**a property being *named*** from **a measurable value being *stated***: a `MENTIONS`
edge fires for both, so a bare mention was treated as evidence of a missed
observation. This drives `false_possible_miss_rate` up (genuine gaps flagged as
misses). This ADR records the port of the `science_ball` USP work that closes it,
adapted to SOTA's architecture, plus the objective benchmark that measures it.

## Decisions

1. **Measurable-value-in-mention detector (N2/A7).** `kg_retrievers.value_in_mention`
   is an offline, LLM-optional regex: a sentence naming the property, containing a
   numeric token, with no RU/EN negation/deferral cue → a value is stated. At
   ingest the pipeline stamps `value_present` on the prose
   `Chunk-[:MENTIONS]->Property` edge (a typed Kuzu `Rel` column; NULL on
   structural/catalog/pre-N2 edges). Computed for every ingest — the gate is what
   *acts* on it.

2. **Opt-in value gate (`absence_value_gate`, default off).** `classify_cell` stays a
   pure primitive with an explicit `value_gate` kwarg; the §25.13 orchestration
   entry `annotate_gaps` resolves it from config when unset, so the flag flows from
   `Settings` to the production surface. **SOTA-specific refinement:** SOTA's
   `is_mentioned_without_observation` is *material-level* (coarse), so an
   un-discussed property (`ABSENT`) reaches `possible_miss`. `mention_value_status`
   therefore returns `False` (→ `genuine_gap`) not only when every prose mention is
   flagged valueless, but also when the property is **never co-mentioned** in the
   discussed material's prose — a property-aware refinement the material-level
   signal lacks. It stays conservative (`None`, no downgrade) on unknown/structural
   edges: "do not downgrade on absence of evidence."

3. **N1 honest recall prior — adapted, not copied.** `science_ball` floored a fixed
   *modality* prose prior (0.55→0.15) because its verdict used it. SOTA's
   `recall_priors` are **empirical Beta over `target_type`** with no chunk-vs-table
   `kind`, and `classify_cell` uses a fixed `MENTION_EXISTS_PRIOR=0.9` for mentioned
   cells — so SOTA is **immune to the §33.9 abstain-collapse** by design. The N1
   adaptation is therefore two-part: (a) `recall_priors.smoothed_recall` gains an
   opt-in `committed_recall_cap` (the telemetry counts *candidates proposed*, not
   *Observations committed*, so recall overstates — the cap clamps it); (b) the
   modality prior + committed floor lives in the **benchmark** recall model
   (`kg_eval.recall_model`), which the Track-A guardrail uses. `Settings.
   prose_observations_committed()` maps the flag to `False`/`None` (never `True`).

4. **N3 prose→Observation — audit + minimal gate.** *Audit finding:* the ingestion
   pipeline materialises prose numerics as `Measurement`s whose `review_needed` is
   set **only** by physical-range validation (`Evidence.source_type` is hard-coded
   `"paragraph"`), so an in-range prose value **auto-commits** — prose is not
   review-gated by provenance. *Fix:* opt-in `prose_observation_extraction` (default
   off) review-gates every prose numeric measurement (never an accepted fact without
   a human). Offline-safe, flag-off = legacy, idempotent under re-ingest.

5. **Track-C benchmark (`kg_eval`).** A deterministic synthetic corpus (six
   archetypes, content-hash seeded, no RNG) seeds a Kuzu store directly with exactly
   the signals `classify_cell` reads, so the **real** absence layer is scored
   offline. The harness reports a confusion matrix, per-class P/R/F1, macro-F1,
   business metrics, calibration (Brier/ECE/AUROC/AUPRC + bootstrap CIs), a
   cost-based threshold study (held-out, never written back), Track-A semantic
   matching, the recall guardrail, and profile-aware honest findings. `python -m
   kg_eval.run_benchmark [--regression]` writes `report.json`/`report.md` and exits 1
   on a reproduced regression.

## Consequence

On the 48-cell synthetic set the base layer scores macro-F1 0.636 with
`false_possible_miss_rate = 1.0` (the exposed weakness); the value oracle and the
**real production gate** both reach macro-F1 1.0 / rate 0.0, and the offline regex
approximates at 0.843 (matching the reference). Every flag is default-off and
independent, so existing §25 pins stay green; enabling them composes N1 (honest
prior) → N2 (value gate) → N3 (prose review-gating) toward the same USP.
