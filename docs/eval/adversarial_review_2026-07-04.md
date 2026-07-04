# Adversarial Review — 2026-07-04

15-finder multi-agent sweep (dimensions × regions), every finding refuted-by-default and
reproduced against the live app. **56 raw findings → 41 CONFIRMED, 4 refuted.**
Severity of confirmed: **3 critical, ~10 high, ~18 medium, ~10 low** (after dedup).

## CRITICAL — fixed ✅ (commit this batch)

- **C-1** `long_term_memory.py` — whole `/api/v1/memory/{user_id}` API had **no auth**; anyone
  (no token) could read/write/delete any user's memory, and a poisoned `alias` personalises the
  victim's next session (§13.20 entity-resolution). **FIX:** `_authorize()` on all 5 endpoints —
  anonymous→401, cross-user→403, privileged (admin/curator) allowed. *Verified live.*
- **C-2** `documents.py` — GET `/{doc_id:path}/...` unauthenticated + `_sidecar` only stripped
  `:`, so `../../secret` traversed out of `uploads/` → arbitrary `.json` read. **FIX:** collapse
  every non-safe char (kills `/`), strip leading dots, assert resolved path stays in `uploads/`.
  *Verified live (traversal → 404).*
- **C-3** `config.py:143` — committed default HS256 `JWT_SECRET` lets anyone forge admin tokens.
  **Note:** already fail-fast-guarded in prod (`config.py:162`); dev-only exposure. **TODO** in
  fix-batch: per-process random dev secret.

## HIGH — pending

- **H-2** `contradiction_scan.py:99` — `str.format()` on Cypher map-literals → `KeyError` → every
  endpoint 500 (feature §13.15 fully dead, kills `ContradictionScanView`). **FIXED ✅** (`{extra}`
  token replace). *Verified 200 live.*
- **H-1** `collaboration.py` investigations IDOR — any authed user (incl. `external_partner`) can
  read (`:193`), enumerate all (`all_visible=true`, `:183`), and PATCH-hijack (`:206`) any
  investigation; no owner/member check. **FIX:** require actor∈{owner,members}; `all_visible` → curator+.
- **H-3** `crosslingual_search.py` — `/status` + `/search` embed the entire 152k-node graph per
  request (no LIMIT, uncached, cache-key=len during ingest) → hang/OOM/DoS.
- **H-4** `graph_retriever.py:164` — "отечественная"/geo filter zeroes ALL non-Paper facts, and
  (`:156`) drops `practice_type="global"` sources → hides applicable peer-reviewed evidence.
- **H-5** `answer_validator.py:80` — flags ANY bare number (years, counts, pH, ordinals) as
  uncited → verifier forces "unverified" + caps confidence ≤0.5 even when every citation is grounded.
- **H-6** `units.py:149` — `parse_numeric_constraints` parses space/NBSP/narrow-NBSP thousands as 0
  → drops magnitude + fabricates a bogus second constraint.
- **H-7** `materials_ner.py:546` — `fuse_mentions` widens char span on partial-overlap merge but
  never updates `.text` → `text != source[start:end]` (provenance/highlight corruption).
- **H-8** `chat.py:190` — chat SSE 404s for token-auth users (EventSource can't send Authorization).
- **H-9** `gds_live.py:42` — all GDS endpoints share one fixed projection name, drop-then-project,
  no lock → concurrent requests corrupt each other.
- **H-10** `coverage_matrix.py:248` — timeline measurement/gap counts use a nonexistent rel-path
  (`Measurement/Gap -SUPPORTED_BY-> Paper`) → silently flatline at ~0.

## MEDIUM (18) & LOW (10) — pending

admin/* unauthenticated incl. mutating POST (`admin.py:39`); comment promote/status no authz
(`collaboration.py:153`); stream resume/backpressure dead code (no `id:` on SSE); no SSE
heartbeat (`research.py:166`); client-disconnect doesn't cancel fan-out (`advisor.py:301`);
`confidence_calibration/translate` slow default path; `confidence_fusion` conflicts≈0;
`/query/stream` ignores geography (`query.py:53`); `App.tsx:379` setView in render;
`units.py:204` density→mg/L ×1000; AdvisorView EventSource leak; advisor fake `fit_score=50`;
verifier caps confidence for incidental numbers; `chat_sessions.py:167` seq race;
`/gaps/absence` truncates before sort; temporal filter ignores `node['year']`; VoI screen
hangs; `/experiments` always empty (wrong labels/rels). LOW: `/query/stream` SSE shape;
`search` filters.property ignored; numeric upper-bound-0 falsy `or`; verifier_retry inert;
callHistory id collision + stale geography; OSS allowlist admits closed models under vendor
prefixes; gds-live `limit` vs `k` param; property-graph missing rel types; LargeGraphView
setTimeout leak; ProseClaims slow-mount spinner.

## Refuted (4)
voi.py "unbounded" (has `scan_limit` break); + 3 others that had guards the finder missed.

## Completeness critic — not yet swept
44 untracked `kg_common/metadata/*` governance/PII modules (uncommitted); `kg_er/` merge
semantics; thin services (curation/search/graph/extraction/ingestion); numeric precision /
unit-conversion stack; embedded-store concurrency; 137k-graph performance/pagination;
timezone math; i18n/Cyrillic escaping; schema migrations.
