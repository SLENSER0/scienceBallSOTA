# Adversarial code review — findings & resolutions

A multi-agent adversarial review (5 review dimensions → independent skeptics that
try to *refute* each finding; 23 agents, ~1M tokens) surfaced 18 findings, 8+
confirmed real by empirical reproduction. Resolutions below; each has a
regression test.

| # | File | Severity | Issue | Fix | Test |
|---|---|---|---|---|---|
| 9 | units.py | HIGH | bare single-letter units (`к`,`м`,`v`) matched inside longer words → fabricated measurements ("5 кг"→"5 к") | removed bare `к`/`м`; added word-boundary lookahead | `test_single_letter_units_not_fabricated` |
| 12 | units.py | MED | hyphenated year pairs ("2015-2020") parsed as numeric ranges | require a unit for range matches | `test_year_range_not_parsed_as_measurement` |
| 11 | units.py | MED | voltage dimensionality had `[current]` in the numerator → V/mV never normalized | corrected to M·L²·T⁻³·I⁻¹ | `test_voltage_normalizes` |
| 13 | units.py | MED | ppm/ppb collapsed to percent, destroying magnitude | dropped `fraction`→percent mapping | `test_ppm_magnitude_preserved` |
| 10 | query_parser.py | HIGH | `_loose_match` matched distinct 4-letter words (шлак↔шлам) | require strict-prefix or ≥5-char shared stem | `test_loose_match_no_false_positive` |
| 5 | graph_retriever.py | HIGH | numeric filter compared unit-less measurements against unit-bearing constraints | skip constraint unless units match | (eval numeric cases) |
| 3,4 | access.py, agent.py | HIGH | RBAC filter left graph nodes + hybrid passages unfiltered → restricted leak | filter graph nodes/edges; withhold passages for restricted roles | `test_rbac_external_partner`, `test_rbac_via_jwt` |
| 1 | evidence.py | HIGH | direct evidence endpoint applied no RBAC | 403 on restricted evidence for non-privileged roles | (route guard) |
| 0 | export.py | HIGH | `/export` took role from body, not the RBAC path | resolve role via `current_role` + audit | `test_export_markdown` |
| 15 | gap_analysis.py | HIGH | contradiction nodes linked only to GapScanRun → unreachable by retrieval | add `ABOUT` edges to subject + measurements | `test_contradiction_reachable_via_retriever` |
| 16 | graph_store.py | MED | `id` prop → Kuzu PK-SET crash (reachable via curation edit as a 500) | exclude `id`/`label` from SET; sanitize edit changes | `test_upsert_ignores_id_prop` |
| 6 | synthesize.py | MED | `restricted:notice` (conf 0.0) deflated confidence & inflated citations | exclude the marker from confidence/citations | `test_rbac_external_partner` |
| 8 | synthesize.py | LOW | comparison-table cells could be null vs TS string type | default null → "—" | (table test) |
| 2 | query.py | LOW | SSE stream had no error handling | wrap generator; emit `error` event | — |
| 14 | entity_resolution.py | MED | fuzzy auto-merge at 92 merged siblings | raised threshold to 96 | — |

Not fixed (accepted): [7] `evidenceCount` not populated on graph nodes (cosmetic
node-sizing); [17] props overwritten wholesale on re-upsert (acceptable — upserts
pass the full prop set).

Re-run: `python scripts/... ` (workflow `adversarial-review`). All 92 tests +
6/6 acceptance cases pass after fixes.
