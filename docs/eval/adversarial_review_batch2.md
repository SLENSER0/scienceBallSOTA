# Adversarial review — auto-generated feature modules (batch 2)

Five modules produced by the parallel feature workflow were each probed by an
independent adversarial agent that **executed real inputs** (not static review)
to confirm every finding. Result: **5 confirmed bugs**, all fixed with
regression tests; full suite 157 → 171 green.

| # | Module | Bug (confirmed by execution) | Fix | Regression test |
|---|--------|------------------------------|-----|-----------------|
| 1 | `domain_templates.py:199` | Ion filter matched symbols against `property_name` too; `Co`/`Ti` are substrings of `"concentration"`, so any absent ion returned **all** ion measurements. | Match ion terms against the measurement `name` only. | `test_water_ion_filter_no_substring_overmatch` |
| 2 | `confidence_of_absence.py:184` | `scan_absence(min_confidence<0.66)` was silently clamped to the hardcoded `CONFIDENT_THRESHOLD`, so `POSSIBLE_ABSENCE` cells never surfaced. | Gate on the caller's numeric threshold; keep COVERED/UNKNOWN excluded. | `test_scan_absence_honors_low_min_confidence` |
| 3 | `entity_index.py:151` | Empty/blank query hit a dead `if not vec` guard (embedder maps `""`→`" "`) and returned arbitrary neighbours. | Guard the input string before embedding. | (covered via `test_entity_index`) |
| 4 | `lab_import.py:_to_float` | RU space/NBSP thousands (`"1 250"`, the default Russian Excel format) parsed to `None` → high values invisible to numeric search. Also `exp_key` omitted `lab`/`expert`, merging distinct labs' experiments. | Fold Unicode spaces + parse `a-b` ranges to midpoint; add lab/expert to the key. | `test_to_float_ru_number_formats`, `test_distinct_labs_are_not_merged` |
| 5 | `seed.py:292,506` | Seed stored `"A/m2"`/`"%"` while `units.to_canonical` emits `"A/m^2"`/`"percent"`, so agent numeric-filter returned **0 results** for 2 of 5 unit families on the §24 demo graph (production path was fine). | Seed writes canonical units. | `test_seed_measurement_units_are_canonical` |

## Method

`Agent` tool, 5 parallel `general-purpose` subagents, each instructed to find
only **empirically confirmed** correctness bugs (run a probe, observe wrong
output) and to not edit source. Probes preserved under the job tmp dir.

## Not-a-bug findings worth noting

- **Same-unit constraint conjunction** (`tools.py` `_passes_numeric`): constraints
  sharing a normalized unit AND-conjoin, so a `≤1000 mg/L` TDS measurement is
  dropped when a tighter `200–300 mg/L` range on a *different* property coexists.
  Test-sanctioned + documented — intended, tracked as a future refinement
  (target constraints by property, not just unit).
- **qdrant single-instance-per-path**: `EntityVectorIndex` and the chunk
  `VectorStore` both open the same on-disk qdrant path; constructing both in one
  process conflicts. Shared architectural limitation of the embedded profile
  (server profile uses a qdrant service). Tracked, not a logic error.
